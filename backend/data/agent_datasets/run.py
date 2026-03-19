"""
Agent dataset generation orchestrator

Reads processed/generated features and produces per-agent training CSVs in
`backend/data/final_training/`.
"""
from pathlib import Path
import pandas as pd
import shutil
import os
import math
import numpy as np

# Allow full-data mode via environment variable to skip safe sampling
FULL_DATA = True  # force full-data mode for thorough retrain (disable sampling)


def ensure_user_id(df, src=None):
    """Ensure dataframe has a `user_id` column by renaming common variants
    or creating a sequential id if none found."""
    if df is None or df.empty:
        return df
    cols = [c.lower() for c in df.columns]
    mapping = {
        'student_id': 'user_id',
        'studentid': 'user_id',
        'userid': 'user_id',
        'user': 'user_id',
        'anon_id': 'user_id',
        'anonymous_id': 'user_id',
    }
    for c in df.columns:
        lc = c.lower()
        if lc in mapping:
            df = df.rename(columns={c: 'user_id'})
            return df
    # try to detect numeric id-like columns
    for c in df.columns:
        if df[c].dtype.kind in 'iu' and c.lower().endswith(('id', '_id')):
            df = df.rename(columns={c: 'user_id'})
            return df
    # no id-like column found: create sequential user ids
    df = df.reset_index(drop=True)
    df['user_id'] = np.arange(1, len(df) + 1)
    return df

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / 'processed'
RAW = ROOT / 'raw'
GENERATED = ROOT / 'generated'
FINAL = ROOT / 'final_training'
AGENTS = PROCESSED / 'agents'
FINAL.mkdir(parents=True, exist_ok=True)
AGENTS.mkdir(parents=True, exist_ok=True)


def build_progress():
    # progress uses interactions + item difficulty + session features
    # discover interaction-like CSVs across processed and raw datasets
    candidates = []
    for base in (PROCESSED, RAW):
        if base.exists():
            candidates.extend(list(base.rglob('*.csv')))

    def _is_interaction(path):
        try:
            head = pd.read_csv(path, nrows=5)
        except Exception:
            return False
        cols = [c.lower() for c in head.columns]
        has_user = any(x in cols for x in ('user_id','userid','user','student_id','studentid'))
        has_item = any(x in cols for x in ('question_id','questionid','item_id','itemid','problem_id','content_id','exercise_id'))
        has_time = any('time' in x or 'timestamp' in x or 'date' in x for x in cols)
        return has_user and (has_item or has_time)

    inter_paths = [p for p in candidates if _is_interaction(p)]
    if not inter_paths:
        print('No interactions -> progress empty')
        pd.DataFrame().to_csv(FINAL/'progress_training.csv', index=False)
        return

    dfs = []
    for p in inter_paths:
        try:
            size_mb = p.stat().st_size / (1024 * 1024)
        except Exception:
            size_mb = 0
        if size_mb > 200 and not FULL_DATA:
            print(f'Large file {p.name} ({size_mb:.1f}MB) — sampling 200k rows')
            df_part = pd.read_csv(p, nrows=200000)
        else:
            try:
                df_part = pd.read_csv(p)
            except Exception:
                # try with low_memory fallback
                df_part = pd.read_csv(p, low_memory=False)

        # ensure unique column names first
        def _uniq_cols(cols):
            seen = {}
            out = []
            for c in cols:
                if c in seen:
                    seen[c] += 1
                    out.append(f"{c}_{seen[c]}")
                else:
                    seen[c] = 0
                    out.append(c)
            return out
        df_part.columns = _uniq_cols(list(df_part.columns))
        # standardize column names
        colmap = {}
        for c in df_part.columns:
            lc = c.lower()
            if lc in ('user_id','userid','student_id','studentid') or lc == 'user':
                colmap[c] = 'user_id'
            if lc in ('question_id','questionid','item_id','itemid','problem_id','content_id','exercise_id'):
                colmap[c] = 'question_id'
            if 'timestamp' in lc or 'time' in lc or 'date' in lc:
                colmap[c] = 'timestamp'
            if lc in ('correct','is_correct','answered_correctly','outcome','score'):
                colmap[c] = 'correct'

        df_part = df_part.rename(columns=colmap)
        # ensure a user_id exists (rename student_id etc or create sequential ids)
        df_part = ensure_user_id(df_part, p.name)
        dfs.append(df_part)

    if not dfs:
        print('No readable interaction tables -> progress empty')
        pd.DataFrame().to_csv(FINAL/'progress_training.csv', index=False)
        return

    # to avoid concat issues with large or irregular frames, write parts to a temp CSV and read back
    temp_path = FINAL / 'progress_parts.csv'
    if temp_path.exists():
        temp_path.unlink()
    for i, part in enumerate(dfs):
        part.to_csv(temp_path, index=False, mode='w' if i == 0 else 'a', header=(i == 0))

    # read combined file with safe sampling
    try:
        size_mb = temp_path.stat().st_size / (1024 * 1024)
    except Exception:
        size_mb = 0
    if size_mb > 500 and not FULL_DATA:
        print(f'Combined interactions large ({size_mb:.1f}MB) — sampling first 400k rows')
        df = pd.read_csv(temp_path, nrows=400000, engine='python', on_bad_lines='skip')
    else:
        df = pd.read_csv(temp_path, engine='python', on_bad_lines='skip')
    # merge generated features if present
    if (GENERATED/'item_difficulty.csv').exists() and 'question_id' in df.columns:
        idf = pd.read_csv(GENERATED/'item_difficulty.csv')
        if 'question_id' in idf.columns:
            df = df.merge(idf[['question_id','difficulty']], on='question_id', how='left')
    if (GENERATED/'session_time_features.csv').exists() and 'user_id' in df.columns:
        sf = pd.read_csv(GENERATED/'session_time_features.csv')
        df = df.merge(sf, on='user_id', how='left')

    # cleaning: require user_id, impute missing, clip outliers
    def _clean_dataframe(df, require=None):
        if df is None or df.empty:
            return df
        # normalize column names
        df.columns = [c.strip() for c in df.columns]
        if require:
            miss_req = [c for c in require if c not in df.columns]
            if miss_req:
                # if essential columns missing, return empty
                print('Missing required columns for cleaning:', miss_req)
                return pd.DataFrame()
        # drop rows missing user_id if present
        if 'user_id' in df.columns:
            df = df[df['user_id'].notna()]
        # numeric imputation
        numcols = df.select_dtypes(include=[np.number]).columns.tolist()
        for c in numcols:
            med = df[c].median(skipna=True)
            if pd.isna(med):
                med = 0
            df[c] = df[c].fillna(med)
            # clip extreme outliers to 1st-99th percentile
            try:
                lo = df[c].quantile(0.01)
                hi = df[c].quantile(0.99)
                df[c] = df[c].clip(lower=lo, upper=hi)
            except Exception:
                pass
        # categorical imputation
        objcols = df.select_dtypes(include=['object']).columns.tolist()
        for c in objcols:
            df[c] = df[c].fillna('unknown')
        return df

    df = _clean_dataframe(df, require=['user_id'])
    FINAL.mkdir(parents=True, exist_ok=True)
    df.to_csv(FINAL/'progress_training.csv', index=False)
    print('Wrote', FINAL/'progress_training.csv', 'rows=', len(df))


def build_profiling():
    # profiling uses user mastery and ability
    parts = []
    # collect any user-level files from generated, processed, or raw
    candidates = []
    if (GENERATED).exists():
        candidates.extend(list(GENERATED.glob('*.csv')))
    if PROCESSED.exists():
        candidates.extend([p for p in PROCESSED.rglob('*.csv') if 'user' in p.name.lower() or 'profile' in p.name.lower() or 'mastery' in p.name.lower()])
    if RAW.exists():
        candidates.extend([p for p in RAW.rglob('*.csv') if 'user' in p.name.lower() or 'profile' in p.name.lower() or 'mastery' in p.name.lower() or 'student' in p.name.lower()])
    for p in candidates:
        try:
            dfp = pd.read_csv(p, nrows=5)
        except Exception:
            continue
        cols = [c.lower() for c in dfp.columns]
        if any('user' in c for c in cols) or any('student' in c for c in cols):
            try:
                part_df = pd.read_csv(p)
            except Exception:
                try:
                    part_df = pd.read_csv(p, low_memory=False)
                except Exception:
                    continue
            # ensure user id exists
            part_df = ensure_user_id(part_df, p.name)
            parts.append(part_df)
    if parts:
        # try to merge on user_id or user column
        df = parts[0]
        for p in parts[1:]:
            common = set(df.columns).intersection(set(p.columns))
            key = None
            for k in ('user_id','userid','user'):
                if k in common:
                    key = k
                    break
            if key:
                df = df.merge(p, on=key, how='outer')
            else:
                # try to align by index-length if no key
                df = pd.concat([df, p], axis=1)
        # cleaning for profiling: require user_id
        def _clean_dataframe(df, require=None):
            if df is None or df.empty:
                return df
            df.columns = [c.strip() for c in df.columns]
            if require:
                miss_req = [c for c in require if c not in df.columns]
                if miss_req:
                    print('Missing required columns for profiling:', miss_req)
                    return pd.DataFrame()
            if 'user_id' in df.columns:
                df = df[df['user_id'].notna()]
            numcols = df.select_dtypes(include=[np.number]).columns.tolist()
            for c in numcols:
                med = df[c].median(skipna=True)
                if pd.isna(med):
                    med = 0
                df[c] = df[c].fillna(med)
                try:
                    lo = df[c].quantile(0.01)
                    hi = df[c].quantile(0.99)
                    df[c] = df[c].clip(lower=lo, upper=hi)
                except Exception:
                    pass
            objcols = df.select_dtypes(include=['object']).columns.tolist()
            for c in objcols:
                df[c] = df[c].fillna('unknown')
            return df

        df = _clean_dataframe(df, require=['user_id'])
        FINAL.mkdir(parents=True, exist_ok=True)
        df.to_csv(FINAL/'profiling_training.csv', index=False)
        print('Wrote', FINAL/'profiling_training.csv', 'rows=', len(df))
    else:
        pd.DataFrame().to_csv(FINAL/'profiling_training.csv', index=False)


def build_motivation():
    # heuristic: try to find stress/motivation labelled datasets in RAW
    candidates = []
    if RAW.exists():
        candidates.extend([p for p in RAW.rglob('*.csv') if 'stress' in p.name.lower() or 'motivation' in p.name.lower() or 'motivate' in p.name.lower()])
    parts = []
    for p in candidates:
        try:
            parts.append(pd.read_csv(p))
        except Exception:
            try:
                parts.append(pd.read_csv(p, low_memory=False))
            except Exception:
                continue
    if parts:
        df = pd.concat(parts, ignore_index=True, sort=False)
        # cleaning: impute and fill, don't require specific columns here
        def _clean_any(df):
            if df is None or df.empty:
                return df
            df.columns = [c.strip() for c in df.columns]
            numcols = df.select_dtypes(include=[np.number]).columns.tolist()
            for c in numcols:
                med = df[c].median(skipna=True)
                if pd.isna(med):
                    med = 0
                df[c] = df[c].fillna(med)
                try:
                    lo = df[c].quantile(0.01)
                    hi = df[c].quantile(0.99)
                    df[c] = df[c].clip(lower=lo, upper=hi)
                except Exception:
                    pass
            objcols = df.select_dtypes(include=['object']).columns.tolist()
            for c in objcols:
                df[c] = df[c].fillna('unknown')
            return df

        df = _clean_any(df)
        FINAL.mkdir(parents=True, exist_ok=True)
        df.to_csv(FINAL/'motivation_training.csv', index=False)
        print('Wrote', FINAL/'motivation_training.csv', 'rows=', len(df))
    else:
        pd.DataFrame().to_csv(FINAL/'motivation_training.csv', index=False)
        print('Wrote empty motivation_training.csv')


def build_reschedule():
    # RL transitions approximated from interactions spacing
    # build reschedule using all interaction-like files across processed/raw
    candidates = []
    for base in (PROCESSED, RAW):
        if base.exists():
            candidates.extend(list(base.rglob('*.csv')))

    def _is_interaction(path):
        try:
            head = pd.read_csv(path, nrows=5)
        except Exception:
            return False
        cols = [c.lower() for c in head.columns]
        has_user = any(x in cols for x in ('user_id','userid','user','student_id','studentid'))
        has_time = any('time' in x or 'timestamp' in x or 'date' in x for x in cols)
        return has_user and has_time

    inter_paths = [p for p in candidates if _is_interaction(p)]
    if not inter_paths:
        pd.DataFrame().to_csv(FINAL/'reschedule_training.csv', index=False)
        return

    dfs = []
    for p in inter_paths:
        try:
            size_mb = p.stat().st_size / (1024 * 1024)
        except Exception:
            size_mb = 0
        if size_mb > 200 and not FULL_DATA:
            df_part = pd.read_csv(p, nrows=200000)
        else:
            try:
                df_part = pd.read_csv(p)
            except Exception:
                df_part = pd.read_csv(p, low_memory=False)
        # rename timestamp-like column
        colmap = {}
        for c in df_part.columns:
            lc = c.lower()
            if 'timestamp' in lc or 'time' in lc or 'date' in lc:
                colmap[c] = 'timestamp'
            if lc in ('user_id','userid','student_id','studentid') or lc == 'user':
                colmap[c] = 'user_id'
        df_part = df_part.rename(columns=colmap)
        # ensure a user_id exists for reschedule parts too
        df_part = ensure_user_id(df_part, p.name)
        dfs.append(df_part)

    if not dfs:
        pd.DataFrame().to_csv(FINAL/'reschedule_training.csv', index=False)
        return

    temp_path = FINAL / 'reschedule_parts.csv'
    if temp_path.exists():
        temp_path.unlink()
    for i, part in enumerate(dfs):
        part.to_csv(temp_path, index=False, mode='w' if i == 0 else 'a', header=(i == 0))
    try:
        size_mb = temp_path.stat().st_size / (1024 * 1024)
    except Exception:
        size_mb = 0
    if size_mb > 500:
        df = pd.read_csv(temp_path, nrows=400000, engine='python', on_bad_lines='skip')
    else:
        df = pd.read_csv(temp_path, engine='python', on_bad_lines='skip')
    # simple: for each user, next-timestamp delta as label
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        if 'user_id' in df.columns:
            df = df.sort_values(['user_id','timestamp'])
        else:
            df = df.sort_values(['timestamp'])
        df['next_ts'] = df.groupby('user_id')['timestamp'].shift(-1)
        df['delta_s'] = (df['next_ts'] - df['timestamp']).dt.total_seconds()
    # clean: require timestamp and user_id for reschedule
    def _clean_reschedule(df):
        if df is None or df.empty:
            return df
        df.columns = [c.strip() for c in df.columns]
        if 'timestamp' not in df.columns or 'user_id' not in df.columns:
            print('Reschedule requires timestamp and user_id; returning empty')
            return pd.DataFrame()
        df = df[df['user_id'].notna() & df['timestamp'].notna()]
        # fill numeric
        numcols = df.select_dtypes(include=[np.number]).columns.tolist()
        for c in numcols:
            med = df[c].median(skipna=True)
            if pd.isna(med):
                med = 0
            df[c] = df[c].fillna(med)
            try:
                lo = df[c].quantile(0.01)
                hi = df[c].quantile(0.99)
                df[c] = df[c].clip(lower=lo, upper=hi)
            except Exception:
                pass
        objcols = df.select_dtypes(include=['object']).columns.tolist()
        for c in objcols:
            df[c] = df[c].fillna('unknown')
        return df

    df = _clean_reschedule(df)
    FINAL.mkdir(parents=True, exist_ok=True)
    df.to_csv(FINAL/'reschedule_training.csv', index=False)
    print('Wrote', FINAL/'reschedule_training.csv', 'rows=', len(df))


def main():
    build_progress()
    build_profiling()
    build_motivation()
    build_reschedule()


if __name__ == '__main__':
    main()
