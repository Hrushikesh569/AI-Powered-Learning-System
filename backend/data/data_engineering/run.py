"""
Data engineering orchestrator

Steps:
- Ingest CSVs from `backend/data/raw/` into `backend/data/processed/interactions.csv`
- Run feature generation: item difficulty, session-time features
- Run advanced features: simple IRT and user mastery

Outputs go to `backend/data/processed/` and `backend/data/generated/`.
"""
from pathlib import Path
import pandas as pd
import numpy as np
import datetime
import os

# use working directory as project root to avoid __file__ resolution issues
PROJECT_ROOT = Path.cwd()
ROOT = PROJECT_ROOT / 'backend' / 'data'
RAW = ROOT / 'raw'
PROCESSED = ROOT / 'processed'
GENERATED = ROOT / 'generated'
PROCESSED.mkdir(parents=True, exist_ok=True)
GENERATED.mkdir(parents=True, exist_ok=True)


def ingest_raw_interactions():
    # collect CSV-like files under RAW and try to extract interactions
    cols = ['user_id','question_id','timestamp','correct']
    records = []
    for p in RAW.rglob('*.csv'):
        try:
            df = pd.read_csv(p, low_memory=False)
        except Exception:
            continue
        # heuristic column mapping
        if 'user_id' in df.columns and ('question_id' in df.columns or 'item_id' in df.columns):
            qcol = 'question_id' if 'question_id' in df.columns else ('item_id' if 'item_id' in df.columns else None)
            tcol = None
            for c in ['timestamp','Time','time','created_at']:
                if c in df.columns:
                    tcol = c; break
            ccol = None
            for c in ['correct','answered_correctly','is_correct','answer_correct']:
                if c in df.columns:
                    ccol = c; break
            if qcol is None or ccol is None:
                continue
            for _, r in df[[ 'user_id', qcol, ccol, tcol ]].fillna('').iterrows():
                try:
                    uid = r['user_id']
                    qid = r[qcol]
                    corr = int(r[ccol]) if r[ccol]!='' else 0
                    ts = r[tcol] if tcol and r[tcol]!='' else None
                except Exception:
                    continue
                records.append({'user_id':uid,'question_id':qid,'correct':corr,'timestamp':ts})
    if not records:
        print('No interaction-like CSVs found in raw')
        return None
    df = pd.DataFrame(records)
    # normalize timestamp
    if 'timestamp' in df.columns:
        try:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        except Exception:
            df['timestamp'] = pd.NaT
    out = PROCESSED / 'interactions.csv'
    df.to_csv(out, index=False)
    print('Wrote', out, 'rows=', len(df))
    return df


def ingest_riiid_train():
    """Stream Riiid `train.csv`, join with `questions.csv`, and write a processed interactions file.
    Produces `processed/interactions_riiid.csv` (appended in chunks).
    """
    riid_root = RAW / 'riiid-test-answer-prediction'
    qfile = riid_root / 'questions.csv'
    trainfile = riid_root / 'train.csv'
    out = PROCESSED / 'interactions_riiid.csv'
    # debug: print existence
    print('DEBUG: riid_root=', riid_root)
    print('DEBUG: questions.csv exists=', qfile.exists(), ' train.csv exists=', trainfile.exists())
    if not qfile.exists() or not trainfile.exists():
        print('Riiid files not found, skipping Riiid ingestion')
        return None
    try:
        qdf = pd.read_csv(qfile)
        qdf = qdf.rename(columns={'question_id':'question_id'})
        qdf['question_id'] = qdf['question_id'].astype(int)
        qmap = qdf.set_index('question_id')[['part','tags','correct_answer']]
    except Exception as e:
        print('Failed to read Riiid questions.csv:', e)
        return None

    chunks = pd.read_csv(trainfile, chunksize=200000)
    written = 0
    # optional limit for quicker/smaller runs (set RIID_MAX_CHUNKS env var)
    max_chunks = None
    try:
        max_chunks = int(os.environ.get('RIID_MAX_CHUNKS'))
    except Exception:
        max_chunks = None
    for i, chunk in enumerate(chunks):
        # keep only question interactions (content_type_id==0)
        if 'content_type_id' in chunk.columns:
            chunk = chunk[chunk['content_type_id'] == 0]
        # normalize column names
        if 'content_id' in chunk.columns:
            chunk = chunk.rename(columns={'content_id':'question_id'})
        # ensure types
        if 'question_id' in chunk.columns:
            chunk['question_id'] = chunk['question_id'].astype(int)
        # join question metadata
        try:
            meta = qmap.reindex(chunk['question_id'].values).reset_index()
            meta.index = chunk.index
            chunk = pd.concat([chunk, meta[['part','tags','correct_answer']]], axis=1)
        except Exception:
            # if join fails, continue with minimal cols
            pass
        # canonicalize output columns
        outdf = pd.DataFrame()
        outdf['user_id'] = chunk.get('user_id')
        # convert timestamp if present
        if 'timestamp' in chunk.columns:
            try:
                outdf['timestamp'] = pd.to_datetime(chunk['timestamp'], unit='ms', errors='coerce')
            except Exception:
                outdf['timestamp'] = pd.to_datetime(chunk['timestamp'], errors='coerce')
        else:
            outdf['timestamp'] = pd.NaT
        outdf['question_id'] = chunk.get('question_id')
        # create `correct` from answered_correctly when available else from correct_answer
        if 'answered_correctly' in chunk.columns:
            outdf['correct'] = chunk['answered_correctly'].fillna(0).astype(int)
        elif 'correct_answer' in chunk.columns and 'user_answer' in chunk.columns:
            outdf['correct'] = (chunk['user_answer'] == chunk['correct_answer']).astype(int)
        else:
            outdf['correct'] = 0
        outdf['dataset'] = 'riiid'
        # append to output file
        if i == 0 and not out.exists():
            outdf.to_csv(out, index=False)
        else:
            outdf.to_csv(out, mode='a', header=False, index=False)
        written += len(outdf)
        print(f'Riiid: processed chunk {i}, rows={len(outdf)}')
        if max_chunks is not None and i + 1 >= max_chunks:
            print(f'RIID_MAX_CHUNKS reached ({max_chunks}), stopping early')
            break
    print('Wrote', out, 'rows=', written)
    try:
        return pd.read_csv(out)
    except Exception:
        return None


def compute_item_difficulty(df: pd.DataFrame):
    if df is None or df.empty:
        print('No interactions to compute item difficulty')
        return
    if 'question_id' not in df.columns or 'correct' not in df.columns:
        return
    qi = df.groupby('question_id')['correct'].agg(['sum','count']).reset_index()
    qi['p'] = qi['sum'] / qi['count']
    eps = 1e-3
    qi['p'] = qi['p'].clip(eps, 1-eps)
    qi['difficulty'] = np.log((1-qi['p'])/qi['p'])
    out = GENERATED / 'item_difficulty.csv'
    qi[['question_id','count','p','difficulty']].to_csv(out, index=False)
    print('Wrote', out)
    return qi


def compute_session_time_features(df: pd.DataFrame):
    if df is None or df.empty or 'timestamp' not in df.columns:
        print('No timestamped interactions for session features')
        return
    # avoid huge in-memory sorts by sampling when dataset is massive
    max_rows_for_full = 5_000_000
    if len(df) > max_rows_for_full:
        print(f'Dataset large ({len(df)} rows) — sampling {max_rows_for_full} rows for session features')
        df = df.sample(n=max_rows_for_full, random_state=1)
    df = df.dropna(subset=['timestamp']).sort_values(['user_id','timestamp'])
    df['ts_prev'] = df.groupby('user_id')['timestamp'].shift(1)
    df['delta'] = (df['timestamp'] - df['ts_prev']).dt.total_seconds().fillna(0)
    sf = df.groupby('user_id')['delta'].agg(['mean','median','std','count']).reset_index()
    sf = sf.rename(columns={'mean':'avg_interaction_gap_s','median':'median_gap_s','std':'std_gap_s','count':'n_interactions'})
    out = GENERATED / 'session_time_features.csv'
    sf.to_csv(out, index=False)
    print('Wrote', out)
    return sf


def compute_advanced_irt_and_mastery(df: pd.DataFrame):
    # simple IRT-like and mastery per user
    if df is None or df.empty:
        return
    if 'question_id' in df.columns and 'correct' in df.columns:
        qi = df.groupby('question_id')['correct'].agg(['sum','count']).reset_index()
        qi['p'] = qi['sum']/qi['count']
        eps=1e-3
        qi['p']=qi['p'].clip(eps,1-eps)
        qi['difficulty']=np.log((1-qi['p'])/qi['p'])
        qi[['question_id','count','p','difficulty']].to_csv(GENERATED/'advanced_irt_item.csv', index=False)
        print('Wrote', GENERATED/'advanced_irt_item.csv')
    if 'user_id' in df.columns and 'correct' in df.columns:
        uu = df.groupby('user_id')['correct'].agg(['sum','count']).reset_index()
        uu['p']=uu['sum']/uu['count']
        eps=1e-3
        uu['p']=uu['p'].clip(eps,1-eps)
        uu['ability']=np.log(uu['p']/(1-uu['p']))
        uu[['user_id','count','p','ability']].to_csv(GENERATED/'advanced_irt_user.csv', index=False)
        # mastery EMA
        rows=[]
        for uid, g in df.groupby('user_id'):
            g = g.sort_values('timestamp') if 'timestamp' in g.columns else g
            corrects = g['correct'].fillna(0).astype(int).values
            recent_5 = pd.Series(corrects).rolling(5, min_periods=1).mean().iloc[-1]
            ema = pd.Series(corrects).ewm(alpha=0.2).mean().iloc[-1]
            rows.append({'user_id':uid,'recent_5':recent_5,'ema':ema,'n':len(corrects)})
        pd.DataFrame(rows).to_csv(GENERATED/'user_mastery.csv', index=False)
        print('Wrote', GENERATED/'user_mastery.csv')


def main():
    # prefer Riiid ingestion (streamed) when available
    df_riiid = ingest_riiid_train()
    if df_riiid is not None:
        df = df_riiid
    else:
        df = ingest_raw_interactions()
    compute_item_difficulty(df)
    compute_session_time_features(df)
    compute_advanced_irt_and_mastery(df)


if __name__ == '__main__':
    main()
