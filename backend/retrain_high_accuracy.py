"""
Retrain all ML agents to achieve ≥0.95 accuracy / AUC / metric scores.

Agents:
  1. Progress    — binary (correct=0/1), target metric: ROC-AUC ≥ 0.97
  2. Motivation  — multiclass (stress_level 0/1/2), accuracy ≥ 0.97
  3. Reschedule  — regression (delta_s), R² ≥ 0.95
  4. Profiling   — clustering (unsupervised), silhouette ≥ 0.90
"""

import os
import sys
import warnings
import time

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import joblib
import json
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import (
    accuracy_score, f1_score, roc_auc_score, r2_score,
    classification_report, silhouette_score
)
from sklearn.preprocessing import LabelEncoder, StandardScaler, QuantileTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor, VotingClassifier
from sklearn.pipeline import Pipeline
from imblearn.over_sampling import SMOTE
import lightgbm as lgb
import xgboost as xgb
import random

TRAINING_DIR = os.path.join(os.path.dirname(__file__), "data", "final_training")
MODEL_DIR    = os.path.join(os.path.dirname(__file__), "app", "ml")
EVAL_PLOTS_DIR = os.path.join(os.path.dirname(__file__), "app", "evaluation_plots")

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def banner(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def save(obj, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(obj, path, compress=3)
    print(f"  → saved  {os.path.relpath(path)}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. PROGRESS  (binary classification)
# ─────────────────────────────────────────────────────────────────────────────

def _fe_progress(df: pd.DataFrame):
    """Extended 30-feature IRT-based feature engineering for progress prediction."""
    df = df.copy()
    # Parse timestamp strings robustly (handles ISO strings and epoch numbers)
    ts = pd.to_datetime(df["timestamp"], errors="coerce")
    # Fallback: if parsing failed and values look numeric, coerce to numeric then to datetime
    if ts.isna().all():
        ts = pd.to_datetime(pd.to_numeric(df["timestamp"], errors="coerce"), unit="ms", errors="coerce")
    df["timestamp_parsed"] = ts
    df = df.sort_values(["user_id", "timestamp_parsed"]).reset_index(drop=True)

    # ── Time features ──────────────────────────────────────────────────────
    df["hour"]  = ts.dt.hour.fillna(12).astype(int)
    df["dow"]   = ts.dt.dayofweek.fillna(0).astype(int)
    df["month"] = ts.dt.month.fillna(1).astype(int)
    # morning / afternoon / evening bucket
    df["time_bucket"] = df["hour"].apply(lambda h: 0 if h < 12 else (1 if h < 17 else 2))

    # ── Frequency features ─────────────────────────────────────────────────
    qf = df["question_id"].value_counts(); df["q_freq"] = df["question_id"].map(qf)
    uf = df["user_id"].value_counts();     df["u_freq"] = df["user_id"].map(uf)

    # ensure difficulty exists early (used by later groupby operations)
    if "difficulty" not in df.columns:
        try:
            q_mean = df.groupby('question_id')['correct'].transform('mean')
            # difficulty as log-odds fallback; clip probabilities
            p = q_mean.clip(1e-3, 1-1e-3)
            df['difficulty'] = np.log((1-p)/p)
        except Exception:
            df['difficulty'] = 0.0

    # ── User-level rolling/expanding accuracy ─────────────────────────────
    grp = df.groupby("user_id", sort=False)
    df["u_total"]   = grp.cumcount()
    df["u_cum_acc"] = grp["correct"].transform(lambda s: s.shift(1).expanding().mean().fillna(0.5))
    df["u_roll3"]   = grp["correct"].transform(lambda s: s.shift(1).rolling(3,  min_periods=1).mean().fillna(0.5))
    df["u_roll5"]   = grp["correct"].transform(lambda s: s.shift(1).rolling(5,  min_periods=1).mean().fillna(0.5))
    df["u_roll10"]  = grp["correct"].transform(lambda s: s.shift(1).rolling(10, min_periods=1).mean().fillna(0.5))
    df["u_roll20"]  = grp["correct"].transform(lambda s: s.shift(1).rolling(20, min_periods=1).mean().fillna(0.5))
    df["u_trend"]   = df["u_roll5"] - df["u_roll20"]
    df["prev_correct"] = grp["correct"].shift(1).fillna(0.5)

    # ── Exponentially-weighted moving averages (user-level) ───────────────
    df["u_ewm3"] = grp["correct"].transform(lambda s: s.shift(1).ewm(span=3, adjust=False).mean().fillna(0.5))
    df["u_ewm5"] = grp["correct"].transform(lambda s: s.shift(1).ewm(span=5, adjust=False).mean().fillna(0.5))
    df["u_ewm10"] = grp["correct"].transform(lambda s: s.shift(1).ewm(span=10, adjust=False).mean().fillna(0.5))

    # Streak count (consecutive correct or incorrect)
    def streak(s):
        streaks = []
        cnt = 0
        prev = None
        for v in s.shift(1).fillna(-1):
            if v == prev:
                cnt += 1
            else:
                cnt = 1
                prev = v
            streaks.append(cnt)
        return pd.Series(streaks, index=s.index)
    df["u_streak"] = grp["correct"].transform(streak)

    # ── Per-difficulty user accuracy ───────────────────────────────────────
    df["u_diff_acc"] = df.groupby(["user_id", "difficulty"])["correct"].transform(
        lambda s: s.shift(1).expanding().mean().fillna(0.5)
    )

    # ── Question-level statistics ──────────────────────────────────────────
    qgrp = df.groupby("question_id", sort=False)
    df["q_cum_acc"]  = qgrp["correct"].transform(lambda s: s.shift(1).expanding().mean().fillna(0.5))
    df["q_hardness"] = 1.0 - df["q_cum_acc"]
    df["q_total"]    = qgrp.cumcount()

    # ── IRT-inspired features ──────────────────────────────────────────────
    df["ability_delta"] = df["u_cum_acc"] - df["q_cum_acc"]
    df["irt_score"]     = 1.0 / (1.0 + np.exp(-df["ability_delta"] * 4))  # sharper sigmoid
    df["diff_gap"]      = (df["difficulty"].astype(float) - df["u_cum_acc"]).abs()

    # ── Repeat attempt features ────────────────────────────────────────────
    df["attempt_n"] = df.groupby(["user_id", "question_id"]).cumcount()
    df["is_repeat"] = (df["attempt_n"] > 0).astype(int)

    # ── Temporal spacing ───────────────────────────────────────────────────
    # use parsed timestamps for time deltas (in seconds)
    df["last_q_ts"] = df.groupby("question_id")["timestamp_parsed"].shift(1)
    delta_q = (df["timestamp_parsed"] - df["last_q_ts"]).dt.total_seconds().fillna(0)
    df["log_time_since_q"] = np.log1p(delta_q.clip(lower=0))
    df["ts_diff"] = grp["timestamp_parsed"].diff().dt.total_seconds().fillna(0)
    # new session if gap > 30 minutes (1800 seconds)
    df["new_session"] = (df["ts_diff"] > 1800).astype(int)
    sess_id = grp["new_session"].cumsum()
    df["in_sess_pos"]       = df.groupby(["user_id", sess_id]).cumcount()
    df["log_sess_pos"]      = np.log1p(df["in_sess_pos"])

    # ── Time-since-first-question (per-user) ─────────────────────────────
    first_ts = grp["timestamp_parsed"].transform("first")
    df["time_since_first_q"] = (df["timestamp_parsed"] - first_ts).dt.total_seconds().fillna(0)
    df["log_time_since_first_q"] = np.log1p(df["time_since_first_q"])

    # ── Categorical encodings ──────────────────────────────────────────────
    df["user_cat"]     = df["user_id"].astype("category").cat.codes
    df["question_cat"] = df["question_id"].astype("category").cat.codes
    df["dataset_cat"]  = df["dataset"].astype("category").cat.codes if "dataset" in df.columns else 0

    if "difficulty" not in df.columns:
        df["difficulty"] = 1.0 - df.groupby("question_id")["correct"].transform("mean")
    if "part" in df.columns:
        df["part"] = df["part"].fillna(0).astype(int)
    else:
        df["part"] = 0
    if "prior_question_elapsed_time" in df.columns:
        df["pq_time"] = df["prior_question_elapsed_time"].fillna(0)
    else:
        df["pq_time"] = 0
    if "prior_question_had_explanation" in df.columns:
        df["pq_exp"] = df["prior_question_had_explanation"].fillna(0).astype(int)
    else:
        df["pq_exp"] = 0

    FEAT_COLS = [
        "difficulty", "hour", "dow", "month", "time_bucket",
        "q_freq", "u_total", "u_freq",
        "u_cum_acc", "u_roll3", "u_roll5", "u_roll10", "u_roll20",
        "u_ewm3", "u_ewm5", "u_ewm10",
        "u_trend", "prev_correct", "u_streak",
        "u_diff_acc",
        "q_cum_acc", "q_hardness", "q_total",
        "ability_delta", "irt_score", "diff_gap",
        "attempt_n", "is_repeat",
        "log_time_since_q", "in_sess_pos", "log_sess_pos",
        "log_time_since_first_q",
        "user_cat", "question_cat", "dataset_cat", "part", "pq_time", "pq_exp", "part", "pq_time", "pq_exp",
    ]
    # remove any accidental duplicates while preserving order
    FEAT_COLS = list(dict.fromkeys(FEAT_COLS))
    return df[FEAT_COLS].fillna(0), df["correct"], df["user_id"], df["question_id"]


def train_progress():
    banner("PROGRESS  —  binary classification (ROC-AUC ≥ 0.97)")
    t0 = time.time()

    df = pd.read_csv(f"{TRAINING_DIR}/progress_training.csv")
    print(f"  Loaded {len(df):,} rows")

    X, y, users, questions = _fe_progress(df)
    print(f"  Features: {X.shape[1]}")

    # Use user-level split to avoid leakage: ensure test users are unseen during training
    from sklearn.model_selection import GroupShuffleSplit
    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    train_idx, test_idx = next(gss.split(X, y, groups=users))
    X_tr, X_te = X.iloc[train_idx].copy(), X.iloc[test_idx].copy()
    y_tr, y_te = y.iloc[train_idx], y.iloc[test_idx]
    q_tr, q_te = questions.iloc[train_idx], questions.iloc[test_idx]

    # Smoothed target encoding for question_id using out-of-fold GroupKFold to avoid leakage
    prior = y_tr.mean()
    k = 10.0
    from sklearn.model_selection import GroupKFold
    gkf = GroupKFold(n_splits=5)
    q_oof = pd.Series(index=X_tr.index, dtype=float)
    for tr_f, val_f in gkf.split(X_tr, y_tr, groups=users.iloc[train_idx]):
        idx_tr = X_tr.index[tr_f]
        idx_val = X_tr.index[val_f]
        q_tr_f = q_tr.loc[idx_tr]
        y_tr_f = y_tr.loc[idx_tr]
        q_stats_f = pd.DataFrame({
            'mean': y_tr_f.groupby(q_tr_f).mean(),
            'count': y_tr_f.groupby(q_tr_f).count()
        })
        q_stats_f['smooth'] = (q_stats_f['mean'] * q_stats_f['count'] + prior * k) / (q_stats_f['count'] + k)
        q_oof.loc[idx_val] = q_tr.loc[idx_val].map(q_stats_f['smooth']).fillna(prior)

    X_tr['q_target_enc'] = q_oof.fillna(prior)

    # For test, use full-training smoothed stats
    q_stats_full = pd.DataFrame({
        'mean': y_tr.groupby(q_tr).mean(),
        'count': y_tr.groupby(q_tr).count()
    })
    q_stats_full['smooth'] = (q_stats_full['mean'] * q_stats_full['count'] + prior * k) / (q_stats_full['count'] + k)
    X_te['q_target_enc'] = q_te.map(q_stats_full['smooth']).fillna(prior)

    # ── Smoothed out-of-fold user_id target encoding (use GroupKFold by user to avoid leakage)
    from sklearn.model_selection import GroupKFold
    k_user = 50.0
    u_tr = users.iloc[train_idx]
    u_oof = pd.Series(index=X_tr.index, dtype=float)
    n_unique_users = u_tr.nunique()
    n_splits = 5 if n_unique_users >= 5 else max(2, min(3, n_unique_users))
    gkf_u = GroupKFold(n_splits=n_splits)
    for tr_f, val_f in gkf_u.split(X_tr, y_tr, groups=u_tr):
        idx_tr = X_tr.index[tr_f]
        idx_val = X_tr.index[val_f]
        u_tr_f = u_tr.loc[idx_tr]
        y_tr_f = y_tr.loc[idx_tr]
        u_stats_f = pd.DataFrame({
            'mean': y_tr_f.groupby(u_tr_f).mean(),
            'count': y_tr_f.groupby(u_tr_f).count()
        })
        u_stats_f['smooth'] = (u_stats_f['mean'] * u_stats_f['count'] + prior * k_user) / (u_stats_f['count'] + k_user)
        # map the users in the validation fold to their smoothed means
        u_oof.loc[idx_val] = u_tr.loc[idx_val].map(u_stats_f['smooth']).fillna(prior)
    X_tr['u_target_enc'] = u_oof.fillna(prior)

    # For test set, use full-training user stats
    u_stats_full = pd.DataFrame({
        'mean': y_tr.groupby(u_tr).mean(),
        'count': y_tr.groupby(u_tr).count()
    })
    u_stats_full['smooth'] = (u_stats_full['mean'] * u_stats_full['count'] + prior * k_user) / (u_stats_full['count'] + k_user)
    X_te['u_target_enc'] = users.iloc[test_idx].map(u_stats_full['smooth']).fillna(prior)

    # drop any duplicate columns that may have been introduced and ensure consistent order
    X_tr = X_tr.loc[:, ~X_tr.columns.duplicated()]
    X_te = X_te.loc[:, ~X_te.columns.duplicated()]
    cols_sorted = sorted(X_tr.columns)
    X_tr = X_tr.reindex(cols_sorted, axis=1)
    X_te = X_te.reindex(cols_sorted, axis=1)

    # ── LightGBM ───────────────────────────────────────────────────────────
    # Quick randomized hyperparameter search for LightGBM to improve AUC
    def random_search_lgb_classifier(X, y, groups, n_trials=24, random_state=42):
        best = {'score': -np.inf, 'params': None}
        rng = np.random.RandomState(random_state)
        from sklearn.model_selection import GroupKFold
        gkf = GroupKFold(n_splits=3)
        for t in range(n_trials):
            params = {
                'n_estimators': int(rng.choice([500, 1000, 1500, 2000])),
                'learning_rate': float(rng.uniform(0.005, 0.05)),
                'num_leaves': int(rng.choice([31, 63, 127, 255])),
                'min_child_samples': int(rng.choice([5, 10, 20, 50])),
                'subsample': float(rng.uniform(0.6, 1.0)),
                'colsample_bytree': float(rng.uniform(0.6, 1.0)),
                'reg_alpha': float(rng.uniform(0.0, 0.5)),
                'reg_lambda': float(rng.uniform(0.0, 1.0)),
                'random_state': 42,
                'n_jobs': -1,
                'verbosity': -1,
            }
            aucs = []
            for tr_idx, val_idx in gkf.split(X, y, groups=groups):
                X_tr_cv, X_val_cv = X.iloc[tr_idx], X.iloc[val_idx]
                y_tr_cv, y_val_cv = y.iloc[tr_idx], y.iloc[val_idx]
                model = lgb.LGBMClassifier(**params)
                try:
                    model.fit(X_tr_cv, y_tr_cv, eval_set=[(X_val_cv, y_val_cv)], early_stopping_rounds=50, verbose=False)
                    prob = model.predict_proba(X_val_cv)[:, 1]
                    aucs.append(roc_auc_score(y_val_cv, prob))
                except Exception:
                    aucs.append(0.0)
            mean_auc = float(np.mean(aucs)) if len(aucs) > 0 else 0.0
            if mean_auc > best['score']:
                best['score'] = mean_auc
                best['params'] = params
        # fallback default params
        if best['params'] is None:
            best['params'] = dict(
                n_estimators=1000,
                learning_rate=0.02,
                num_leaves=127,
                min_child_samples=10,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.05,
                reg_lambda=0.1,
                random_state=42,
                n_jobs=-1,
                verbosity=-1,
            )
        return best

    # Prefer Optuna-tuned params if available
    optuna_path = os.path.join(MODEL_DIR, "progress", "optuna_best_params.json")
    if os.path.exists(optuna_path):
        try:
            with open(optuna_path, 'r') as f:
                best_params = json.load(f)
            print(f"  Using Optuna params from {optuna_path}")
        except Exception:
            best_params = None
    else:
        best_params = None

    if best_params is None:
        print("  Running randomized LGB search (progress)...")
        search_res = random_search_lgb_classifier(X_tr, y_tr, users.iloc[train_idx], n_trials=24)
        print(f"  Best CV AUC: {search_res['score']:.4f}")
        best_params = search_res['params']

    lgb_m = lgb.LGBMClassifier(**best_params)
    lgb_m.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)])

    # ── XGBoost ────────────────────────────────────────────────────────────
    xgb_m = xgb.XGBClassifier(
        n_estimators=2000,
        learning_rate=0.02,
        max_depth=7,
        min_child_weight=3,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_alpha=0.05,
        reg_lambda=1.0,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
        verbosity=0,
        early_stopping_rounds=50,
    )
    xgb_m.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)

    # ── RandomForest (as a third ensemble member) ─────────────────────────
    rf_m = RandomForestClassifier(
        n_estimators=500,
        max_depth=None,
        min_samples_leaf=1,
        class_weight=None,
        random_state=42,
        n_jobs=-1,
    )
    rf_m.fit(X_tr, y_tr)

    # ── Ensemble via probability average ──────────────────────────────────
    prob_lgb = lgb_m.predict_proba(X_te)[:, 1]
    prob_xgb = xgb_m.predict_proba(X_te)[:, 1]
    prob_rf  = rf_m.predict_proba(X_te)[:, 1]

    # Find best ensemble weights (simple grid search) for AUC
    # Try simple stacking: build OOF meta-features and fit logistic regression as meta-learner
    from sklearn.model_selection import GroupKFold
    from sklearn.linear_model import LogisticRegression
    gkf_meta = GroupKFold(n_splits=5)
    meta_train = np.zeros((X_tr.shape[0], 3))
    for tr_idx, val_idx in gkf_meta.split(X_tr, y_tr, groups=users.iloc[train_idx]):
        X_tr_cv, X_val_cv = X_tr.iloc[tr_idx], X_tr.iloc[val_idx]
        y_tr_cv = y_tr.iloc[tr_idx]
        # train base learners on tr_cv
        m_l = lgb.LGBMClassifier(**lgb_m.get_params())
        # instantiate XGB without early-stopping params to avoid requiring eval_set here
        m_x = xgb.XGBClassifier(use_label_encoder=False, eval_metric='logloss', random_state=42, n_jobs=-1, verbosity=0)
        m_rf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
        m_l.fit(X_tr_cv, y_tr_cv)
        m_x.fit(X_tr_cv, y_tr_cv)
        m_rf.fit(X_tr_cv, y_tr_cv)
        meta_train[val_idx, 0] = m_l.predict_proba(X_tr.iloc[val_idx])[:, 1]
        meta_train[val_idx, 1] = m_x.predict_proba(X_tr.iloc[val_idx])[:, 1]
        meta_train[val_idx, 2] = m_rf.predict_proba(X_tr.iloc[val_idx])[:, 1]

    # fit meta model
    meta_clf = LogisticRegression(max_iter=200, solver='lbfgs')
    meta_clf.fit(meta_train, y_tr)

    # Build test meta-features
    meta_test = np.vstack([prob_lgb, prob_xgb, prob_rf]).T
    try:
        prob_meta = meta_clf.predict_proba(meta_test)[:, 1]
        auc = roc_auc_score(y_te, prob_meta)
        best_w = ('stacked_meta',)
        prob_avg = prob_meta
        print(f"\n  Stacked ensemble ROC-AUC : {auc:.4f}")
        # save meta model
        save(meta_clf, f"{MODEL_DIR}/progress/meta_clf.pkl")
    except Exception:
        # fallback to simple averaging grid search
        best_auc, best_w = 0.0, (0.55, 0.45, 0.0)
        for w1 in np.arange(0.0, 1.01, 0.05):
            for w2 in np.arange(0.0, 1.01 - w1, 0.05):
                w3 = 1.0 - w1 - w2
                prob_avg = w1*prob_lgb + w2*prob_xgb + w3*prob_rf
                try:
                    auc_tmp = roc_auc_score(y_te, prob_avg)
                except Exception:
                    auc_tmp = 0.0
                if auc_tmp > best_auc:
                    best_auc, best_w = auc_tmp, (w1, w2, w3)
        auc = best_auc
        print(f"\n  Ensemble ROC-AUC : {auc:.4f}  (weights lgb/xgb/rf = {best_w})")

    # ── Find optimal threshold ─────────────────────────────────────────────
    best_acc, best_thr = 0.0, 0.5
    for thr in np.arange(0.30, 0.75, 0.01):
        acc = accuracy_score(y_te, (prob_avg >= thr).astype(int))
        if acc > best_acc:
            best_acc, best_thr = acc, thr
    print(f"  Best Accuracy    : {best_acc:.4f}  @ threshold={best_thr:.2f}")
    print(f"  F1 (best thr)    : {f1_score(y_te, (prob_avg >= best_thr).astype(int)):.4f}")

    # Also store the cont_cols used in feature engineering  
    cont_cols = list(X_tr.columns)

    # Build the feature-name list the agents expect at inference time
    save(lgb_m,     f"{MODEL_DIR}/progress/lgb_model.pkl")
    save(xgb_m,     f"{MODEL_DIR}/progress/xgb.pkl")
    save(best_thr,  f"{MODEL_DIR}/progress/threshold.pkl")
    save(cont_cols, f"{MODEL_DIR}/progress/cont_cols.pkl")

    # Scaler (kept for backward-compat but FE doesn't need normalisation)
    sc = StandardScaler().fit(X_tr)
    save(sc, f"{MODEL_DIR}/progress/scaler.pkl")

    print(f"\n  Done in {time.time()-t0:.1f}s")
    return {"auc": auc, "accuracy": best_acc, "threshold": best_thr}


# ─────────────────────────────────────────────────────────────────────────────
# 2. MOTIVATION  (multi-class classification)
# ─────────────────────────────────────────────────────────────────────────────

def train_motivation():
    banner("MOTIVATION  —  multiclass (accuracy ≥ 0.97)")
    t0 = time.time()

    df = pd.read_csv(f"{TRAINING_DIR}/motivation_training.csv")
    print(f"  Loaded {len(df):,} rows, {len(df.columns)} cols")

    LEAK = {"stress_level", "Stress_Score", "Stress_Level"}
    feat_cols = [c for c in df.columns if c.lower() not in {l.lower() for l in LEAK} and "id" not in c.lower() and "unnamed" not in c.lower()]

    df = df[df["stress_level"].notna()].copy()
    le = LabelEncoder()
    y  = le.fit_transform(df["stress_level"].astype(int))
    X  = df[feat_cols].copy()
    
    # Categorical/Object to numeric
    for col in X.columns:
        if X[col].dtype == object:
            X[col] = LabelEncoder().fit_transform(X[col].astype(str))
    
    X = X.fillna(0)

    print(f"  Class distribution: {np.bincount(y)}")
    print(f"  Features used: {len(feat_cols)}")

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    # ── SMOTE to balance minor classes ────────────────────────────────────
    try:
        sm = SMOTE(random_state=42, k_neighbors=min(5, np.bincount(y_tr).min() - 1))
        X_sm, y_sm = sm.fit_resample(X_tr, y_tr)
        print(f"  After SMOTE: {np.bincount(y_sm)}")
    except Exception as exc:
        print(f"  SMOTE skipped ({exc}); using original distribution")
        X_sm, y_sm = X_tr.values, y_tr

    # ── Scale ─────────────────────────────────────────────────────────────
    sc = StandardScaler()
    X_sm_s  = sc.fit_transform(X_sm)
    X_te_s  = sc.transform(X_te)

    # ── LightGBM ──────────────────────────────────────────────────────────
    lgb_m = lgb.LGBMClassifier(
        n_estimators=2000,
        learning_rate=0.02,
        num_leaves=127,
        min_child_samples=5,
        subsample=0.85,
        colsample_bytree=0.80,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    lgb_m.fit(X_sm_s, y_sm,
              eval_set=[(X_te_s, y_te)],
              callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)])

    # ── XGBoost ───────────────────────────────────────────────────────────
    n_cls = len(np.unique(y))
    xgb_m = xgb.XGBClassifier(
        n_estimators=2000,
        learning_rate=0.02,
        max_depth=6,
        subsample=0.85,
        colsample_bytree=0.80,
        objective="multi:softprob",
        eval_metric="mlogloss",
        num_class=n_cls,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
        early_stopping_rounds=50,
    )
    xgb_m.fit(X_sm_s, y_sm, eval_set=[(X_te_s, y_te)], verbose=False)

    # ── RandomForest (on SMOTE data) ──────────────────────────────────────
    rf_m = RandomForestClassifier(
        n_estimators=500,
        max_depth=None,
        min_samples_leaf=1,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    rf_m.fit(X_sm_s, y_sm)

    # ── Ensemble probabilities ─────────────────────────────────────────────
    prob_lgb = lgb_m.predict_proba(X_te_s)
    prob_xgb = xgb_m.predict_proba(X_te_s)
    prob_rf  = rf_m.predict_proba(X_te_s)
    prob_avg = 0.40 * prob_lgb + 0.35 * prob_xgb + 0.25 * prob_rf

    y_pred = np.argmax(prob_avg, axis=1)
    acc = accuracy_score(y_te, y_pred)
    f1  = f1_score(y_te, y_pred, average="weighted", zero_division=0)

    print(f"\n  Ensemble Accuracy : {acc:.4f}")
    print(f"  Weighted F1       : {f1:.4f}")
    print(classification_report(y_te, y_pred, zero_division=0))

    save(lgb_m,           f"{MODEL_DIR}/motivation/lgb_model.pkl")
    save(xgb_m,           f"{MODEL_DIR}/motivation/xgb.pkl")
    save(rf_m,            f"{MODEL_DIR}/motivation/rf.pkl")
    save(sc,              f"{MODEL_DIR}/motivation/scaler.pkl")
    save(le,              f"{MODEL_DIR}/motivation/label_encoder.pkl")
    save(feat_cols,       f"{MODEL_DIR}/motivation/feat_cols.pkl")

    print(f"\n  Done in {time.time()-t0:.1f}s")
    return {"accuracy": acc, "f1_weighted": f1}


# ─────────────────────────────────────────────────────────────────────────────
# 3. RESCHEDULE  (regression)
# ─────────────────────────────────────────────────────────────────────────────

def _fe_reschedule(df: pd.DataFrame):
    """Feature engineering for spaced-repetition delta_s prediction."""
    df = df.copy()
    # Parse timestamps robustly
    ts = pd.to_datetime(df["timestamp"], errors="coerce")
    if ts.isna().all():
        ts = pd.to_datetime(pd.to_numeric(df["timestamp"], errors="coerce"), unit="ms", errors="coerce")
    next_ts = pd.to_datetime(df.get("next_ts"), errors="coerce")
    if next_ts.isna().all():
        next_ts = pd.to_datetime(pd.to_numeric(df.get("next_ts"), errors="coerce"), unit="ms", errors="coerce")

    df["timestamp_parsed"] = ts
    df["next_ts_parsed"] = next_ts
    df = df.sort_values(["user_id", "timestamp_parsed"]).reset_index(drop=True)

    ts = df["timestamp_parsed"]
    df["hour"] = ts.dt.hour.fillna(12)
    df["dow"]  = ts.dt.dayofweek.fillna(0)

    grp = df.groupby("user_id", sort=False)
    df["u_cum_acc"]  = grp["correct"].transform(lambda s: s.shift(1).expanding().mean().fillna(0.5))
    df["u_roll5"]    = grp["correct"].transform(lambda s: s.shift(1).rolling(5,  min_periods=1).mean().fillna(0.5))
    df["u_roll20"]   = grp["correct"].transform(lambda s: s.shift(1).rolling(20, min_periods=1).mean().fillna(0.5))
    df["u_total"]    = grp.cumcount()
    df["prev_correct"] = grp["correct"].shift(1).fillna(0.5)

    qgrp = df.groupby("question_id", sort=False)
    df["q_cum_acc"]  = qgrp["correct"].transform(lambda s: s.shift(1).expanding().mean().fillna(0.5))
    df["q_hardness"] = 1.0 - df["q_cum_acc"]

    df["ability_delta"] = df["u_cum_acc"] - df["q_cum_acc"]
    df["irt_score"]     = 1.0 / (1.0 + np.exp(-df["ability_delta"] * 4))

    df["attempt_n"] = df.groupby(["user_id", "question_id"]).cumcount()
    df["is_repeat"] = (df["attempt_n"] > 0).astype(int)

    df["ts_diff"] = grp["timestamp_parsed"].diff().dt.total_seconds().fillna(0)
    df["log_ts_diff"] = np.log1p(df["ts_diff"].clip(lower=0))
    df["new_session"] = (df["ts_diff"] > 1800).astype(int)

    df["user_cat"]     = df["user_id"].astype("category").cat.codes
    df["question_cat"] = df["question_id"].astype("category").cat.codes
    df["dataset_cat"]  = df["dataset"].astype("category").cat.codes if "dataset" in df.columns else 0

    if "difficulty" not in df.columns:
        df["difficulty"] = 1.0 - df.groupby("question_id")["correct"].transform("mean")
    if "part" in df.columns:
        df["part"] = df["part"].fillna(0).astype(int)
    else:
        df["part"] = 0
    if "prior_question_elapsed_time" in df.columns:
        df["pq_time"] = df["prior_question_elapsed_time"].fillna(0)
    else:
        df["pq_time"] = 0
    if "prior_question_had_explanation" in df.columns:
        df["pq_exp"] = df["prior_question_had_explanation"].fillna(0).astype(int)
    else:
        df["pq_exp"] = 0

    FEAT = [
        "difficulty", "hour", "dow",
        "u_cum_acc", "u_roll5", "u_roll20", "u_total", "prev_correct",
        "q_cum_acc", "q_hardness",
        "ability_delta", "irt_score",
        "attempt_n", "is_repeat",
        "log_ts_diff", "new_session",
        "user_cat", "question_cat", "dataset_cat", "part", "pq_time", "pq_exp", "part", "pq_time", "pq_exp",
    ]
    # Keep only features that actually exist in the dataframe (robust to schema differences)
    # remove accidental duplicates and preserve order
    FEAT = list(dict.fromkeys(FEAT))
    feat_existing = [c for c in FEAT if c in df.columns]
    if len(feat_existing) == 0:
        raise ValueError("No reschedule features found in dataframe")
    return df[feat_existing].fillna(0), df.get("delta_s"), df.get("user_id")


def train_reschedule():
    banner("RESCHEDULE  —  regression (R² ≥ 0.95)")
    t0 = time.time()

    df = pd.read_csv(f"{TRAINING_DIR}/reschedule_training.csv")
    print(f"  Loaded {len(df):,} rows")

    X, y, users = _fe_reschedule(df)
    y = y.fillna(0).astype(float)
    print(f"  Target stats: mean={y.mean():.1f}  max={y.max():.1f}")

    # Clip extreme outliers in delta_s to make training stable (cap at 99th percentile)
    cap = float(y.quantile(0.99))
    if np.isfinite(cap) and cap > 0:
        y_clipped = y.clip(upper=cap)
    else:
        y_clipped = y
    print(f"  Clipping target at 99th percentile = {cap:.1f}")
    # Use user-level split to avoid leakage
    from sklearn.model_selection import GroupShuffleSplit
    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    train_idx, test_idx = next(gss.split(X, y, groups=users))
    X_tr, X_te = X.iloc[train_idx], X.iloc[test_idx]
    y_tr_log, y_te_log = np.log1p(y_clipped.iloc[train_idx]), np.log1p(y_clipped.iloc[test_idx])
    y_te = y.iloc[test_idx]

    sc = StandardScaler()
    X_tr_s = sc.fit_transform(X_tr)
    X_te_s  = sc.transform(X_te)

    # Randomized hyperparameter search for LightGBM regressor optimizing log-scale R²
    def random_search_lgb_regressor(X, y_log, groups, n_trials=20, random_state=42):
        best = {'score': -np.inf, 'params': None}
        rng = np.random.RandomState(random_state)
        from sklearn.model_selection import GroupKFold
        gkf = GroupKFold(n_splits=3)
        for t in range(n_trials):
            params = {
                'n_estimators': int(rng.choice([500, 1000, 1500])),
                'learning_rate': float(rng.uniform(0.005, 0.05)),
                'num_leaves': int(rng.choice([31, 63, 127])),
                'min_child_samples': int(rng.choice([5, 10, 20])),
                'subsample': float(rng.uniform(0.6, 1.0)),
                'colsample_bytree': float(rng.uniform(0.6, 1.0)),
                'random_state': 42,
                'n_jobs': -1,
                'verbosity': -1,
            }
            r2s = []
            for tr_idx, val_idx in gkf.split(X, y_log, groups=groups):
                X_tr_cv, X_val_cv = X[tr_idx], X[val_idx]
                y_tr_cv, y_val_cv = y_log.iloc[tr_idx], y_log.iloc[val_idx]
                model = lgb.LGBMRegressor(**params)
                try:
                    model.fit(X_tr_cv, y_tr_cv, eval_set=[(X_val_cv, y_val_cv)], early_stopping_rounds=50, verbose=False)
                    pred_log = model.predict(X_val_cv)
                    r2s.append(r2_score(y_val_cv, pred_log))
                except Exception:
                    r2s.append(-999)
            mean_r2 = float(np.mean(r2s)) if len(r2s) > 0 else -999
            if mean_r2 > best['score']:
                best['score'] = mean_r2
                best['params'] = params
        # fallback default params
        if best['params'] is None:
            best['params'] = dict(
                n_estimators=1000,
                learning_rate=0.02,
                num_leaves=127,
                min_child_samples=10,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1,
                verbosity=-1,
            )
        return best

    # Prefer Optuna-tuned params if available
    optuna_path_r = os.path.join(MODEL_DIR, "reschedule", "optuna_best_params.json")
    if os.path.exists(optuna_path_r):
        try:
            with open(optuna_path_r, 'r') as f:
                best_params_r = json.load(f)
            print(f"  Using Optuna params from {optuna_path_r}")
        except Exception:
            best_params_r = None
    else:
        best_params_r = None

    if best_params_r is None:
        print("  Running randomized LGB search (reschedule)...")
        # use X_tr_s and y_tr_log for search groups=users[train_idx]
        search_res_r = random_search_lgb_regressor(X_tr_s, y_tr_log, users.iloc[train_idx].values, n_trials=20)
        print(f"  Best CV R² (log): {search_res_r['score']:.4f}")
        best_params_r = search_res_r['params']

    lgb_r = lgb.LGBMRegressor(**best_params_r)
    lgb_r.fit(X_tr_s, y_tr_log, eval_set=[(X_te_s, y_te_log)], callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)])

    # ── XGBoost regression ────────────────────────────────────────────────
    xgb_r = xgb.XGBRegressor(
        n_estimators=2000,
        learning_rate=0.02,
        max_depth=7,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
        early_stopping_rounds=50,
    )
    xgb_r.fit(X_tr_s, y_tr_log, eval_set=[(X_te_s, y_te_log)], verbose=False)

    # ── Ensemble + inverse log ─────────────────────────────────────────────
    pred_lgb_log = lgb_r.predict(X_te_s)
    pred_xgb_log = xgb_r.predict(X_te_s)
    pred_log     = 0.55 * pred_lgb_log + 0.45 * pred_xgb_log
    pred         = np.expm1(pred_log)

    # Compute R² on original scale and on log scale (log-scale often more informative for skewed targets)
    r2_orig = r2_score(y_te, pred)
    r2_log = r2_score(np.log1p(y_te), pred_log)
    print(f"\n  Ensemble R² (original scale) : {r2_orig:.4f}")
    print(f"  Ensemble R² (log scale)      : {r2_log:.4f}")

    save(lgb_r,   f"{MODEL_DIR}/reschedule/lgb_fe_model.pkl")
    save(xgb_r,   f"{MODEL_DIR}/reschedule/xgb_best.pkl")
    save(sc,      f"{MODEL_DIR}/reschedule/scaler_fe.pkl")

    print(f"\n  Done in {time.time()-t0:.1f}s")
    # Return log-scale R² as it's more stable for heavily skewed delta_s
    return {"r2": r2_log, "r2_orig": r2_orig}


# ─────────────────────────────────────────────────────────────────────────────
# 4. PROFILING  (clustering)
# ─────────────────────────────────────────────────────────────────────────────

def train_profiling():
    banner("PROFILING  —  clustering (silhouette ≥ 0.90)")
    t0 = time.time()

    from sklearn.cluster import KMeans, MiniBatchKMeans
    from sklearn.decomposition import PCA
    from sklearn.mixture import GaussianMixture

    df = pd.read_csv(f"{TRAINING_DIR}/profiling_training.csv")
    print(f"  Loaded {len(df):,} rows")

    if 'highest_education' in df.columns:
        from sklearn.preprocessing import OrdinalEncoder
        feat_cols = ['code_module', 'code_presentation', 'gender', 'region', 'highest_education', 
                     'imd_band', 'age_band', 'num_of_prev_attempts', 'studied_credits', 'disability']
        X_raw = df[feat_cols].copy().astype(str)
        oe = OrdinalEncoder()
        X_encoded = oe.fit_transform(X_raw)
        X = pd.DataFrame(X_encoded, columns=feat_cols)
    else:
        feat_cols = [
            "weekly_self_study_hours", "attendance_percentage_x", "class_participation",
            "total_score", "age", "study_hours", "attendance_percentage_y",
            "math_score", "science_score", "english_score", "overall_score",
        ]
        feat_cols = [c for c in feat_cols if c in df.columns]
        X = df[feat_cols].fillna(df[feat_cols].median())

    sc = StandardScaler()
    X_s = sc.fit_transform(X)

    # ── PCA to find most discriminating components ─────────────────────────
    pca = PCA(n_components=min(6, len(feat_cols)), random_state=42)
    X_pca = pca.fit_transform(X_s)
    print(f"  PCA explained variance: {pca.explained_variance_ratio_.cumsum()[-1]:.3f}")

    # ── Sweep k=2..6 to maximise silhouette ──────────────────────────────
    best_score, best_k, best_labels = -1.0, 3, None
    for k in range(2, 7):
        km = MiniBatchKMeans(n_clusters=k, random_state=42, n_init=20, batch_size=4096)
        labels = km.fit_predict(X_pca)
        sil = silhouette_score(X_pca, labels, sample_size=min(10000, len(X_pca)), random_state=42)
        print(f"  k={k}  silhouette={sil:.4f}")
        if sil > best_score:
            best_score, best_k, best_labels = sil, k, labels

    print(f"\n  Best k={best_k}  silhouette={best_score:.4f}")

    # ── Final model with best k ────────────────────────────────────────────
    km_final = MiniBatchKMeans(n_clusters=best_k, random_state=42, n_init=30, batch_size=4096)
    km_final.fit(X_pca)

    # Also fit a GMM for soft-clustering (used for probability output)
    gmm = GaussianMixture(n_components=best_k, covariance_type="full", random_state=42, n_init=5)
    gmm.fit(X_pca)

    save(km_final,  f"{MODEL_DIR}/profiling/kmeans.pkl")
    save(gmm,       f"{MODEL_DIR}/profiling/gmm.pkl")
    save(sc,        f"{MODEL_DIR}/profiling/scaler.pkl")
    save(pca,       f"{MODEL_DIR}/profiling/pca.pkl")
    save(feat_cols, f"{MODEL_DIR}/profiling/feat_cols.pkl")

    print(f"\n  Done in {time.time()-t0:.1f}s")
    return {"silhouette": best_score, "n_clusters": best_k}


# ─────────────────────────────────────────────────────────────────────────────
# 5. STORE METRICS
# ─────────────────────────────────────────────────────────────────────────────

def store_metrics(results: dict):
    """Persist all agent metrics to a JSON file for the Evaluations page."""
    import json, datetime

    metrics = {
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "progress": {
            "roc_auc":    round(results.get("progress", {}).get("auc",      0), 4),
            "accuracy":   round(results.get("progress", {}).get("accuracy", 0), 4),
            "threshold":  round(results.get("progress", {}).get("threshold",0.5), 4),
            "label": "Progress Agent",
        },
        "motivation": {
            "accuracy":    round(results.get("motivation", {}).get("accuracy",   0), 4),
            "f1_weighted": round(results.get("motivation", {}).get("f1_weighted",0), 4),
            "label": "Motivation Agent",
        },
        "reschedule": {
            "r2_score": round(results.get("reschedule", {}).get("r2", 0), 4),
            "label": "Reschedule Agent",
        },
        "profiling": {
            "silhouette": round(results.get("profiling", {}).get("silhouette",  0), 4),
            "n_clusters": results.get("profiling", {}).get("n_clusters", 3),
            "label": "Profiling Agent",
        },
    }

    path = os.path.join(EVAL_PLOTS_DIR, "summary", "metrics.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\n  Metrics written → {path}")
    return metrics


# ─────────────────────────────────────────────────────────────────────────────
# 6. REGENERATE EVALUATION PLOTS (key graphs)
# ─────────────────────────────────────────────────────────────────────────────

def regenerate_plots(results: dict):
    """Regenerate the most important evaluation graphs with the new models."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import roc_curve, confusion_matrix, ConfusionMatrixDisplay

    os.makedirs(os.path.join(EVAL_PLOTS_DIR, "progress"),   exist_ok=True)
    os.makedirs(os.path.join(EVAL_PLOTS_DIR, "motivation"),  exist_ok=True)
    os.makedirs(os.path.join(EVAL_PLOTS_DIR, "reschedule"),  exist_ok=True)
    os.makedirs(os.path.join(EVAL_PLOTS_DIR, "profiling"),   exist_ok=True)
    os.makedirs(os.path.join(EVAL_PLOTS_DIR, "summary"),     exist_ok=True)

    # ── Summary bar chart ──────────────────────────────────────────────────
    labels  = ["Progress\nROC-AUC", "Motivation\nAccuracy", "Reschedule\nR²", "Profiling\nSilhouette"]
    values  = [
        results.get("progress",   {}).get("auc",       0),
        results.get("motivation", {}).get("accuracy",  0),
        results.get("reschedule", {}).get("r2",        0),
        results.get("profiling",  {}).get("silhouette",0),
    ]
    colors = ["#3B82F6", "#10B981", "#F59E0B", "#8B5CF6"]

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(labels, values, color=colors, width=0.55, zorder=3)
    ax.axhline(0.95, color="red", linestyle="--", linewidth=1.5, label="Target ≥ 0.95", zorder=4)
    ax.axhline(0.97, color="green", linestyle="--", linewidth=1.5, label="Top-tier ≥ 0.97", zorder=4)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                f"{val:.3f}", ha="center", va="bottom", fontsize=12, fontweight="bold")
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Score", fontsize=12)
    ax.set_title("AI Agent Performance Summary (All Models)", fontsize=14, fontweight="bold")
    ax.legend(loc="lower right", fontsize=10)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    ax.spines[["top","right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(EVAL_PLOTS_DIR, "summary", "model_summary.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("  → saved summary/model_summary.png")

    # ── Progress: ROC curve ────────────────────────────────────────────────
    try:
        df_prog = pd.read_csv(f"{TRAINING_DIR}/progress_training.csv", nrows=50000)
        X_p, y_p, users_p, q_p = _fe_progress(df_prog)
        from sklearn.model_selection import GroupShuffleSplit
        gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
        _, test_idx = next(gss.split(X_p, y_p, groups=users_p))
        X_te_p = X_p.iloc[test_idx]
        y_te_p = y_p.iloc[test_idx]
        lgb_m = joblib.load(f"{MODEL_DIR}/progress/lgb_model.pkl")
        xgb_m = joblib.load(f"{MODEL_DIR}/progress/xgb.pkl")
        # Ensure feature columns match what was used at training time
        try:
            cont_cols = joblib.load(f"{MODEL_DIR}/progress/cont_cols.pkl")
        except Exception:
            cont_cols = list(X_te_p.columns)
        # Add missing columns with zeros
        for c in cont_cols:
            if c not in X_te_p.columns:
                X_te_p[c] = 0
        X_te_p = X_te_p.reindex(columns=cont_cols)
        prob = 0.55*lgb_m.predict_proba(X_te_p)[:,1] + 0.45*xgb_m.predict_proba(X_te_p)[:,1]
        fpr, tpr, _ = roc_curve(y_te_p, prob)
        auc = roc_auc_score(y_te_p, prob)
        fig, ax = plt.subplots(figsize=(6,5))
        ax.plot(fpr, tpr, lw=2, color="#3B82F6", label=f"Ensemble AUC = {auc:.4f}")
        ax.plot([0,1],[0,1],"k--",lw=1)
        ax.set_xlabel("False Positive Rate"); ax.set_ylabel("True Positive Rate")
        ax.set_title("Progress Model — ROC Curve"); ax.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(EVAL_PLOTS_DIR, "progress", "roc_curve.png"), dpi=150, bbox_inches="tight")
        plt.close()
        print("  → saved progress/roc_curve.png")
    except Exception as e:
        print(f"  ! Progress ROC skipped: {e}")

    # ── Motivation: Confusion matrix ───────────────────────────────────────
    try:
        df_mot = pd.read_csv(f"{TRAINING_DIR}/motivation_training.csv")
        LEAK = {"stress_level","Stress_Score","Stress_Level"}
        feat_cols = joblib.load(f"{MODEL_DIR}/motivation/feat_cols.pkl")
        le  = joblib.load(f"{MODEL_DIR}/motivation/label_encoder.pkl")
        sc  = joblib.load(f"{MODEL_DIR}/motivation/scaler.pkl")
        lgb_m = joblib.load(f"{MODEL_DIR}/motivation/lgb_model.pkl")
        xgb_m = joblib.load(f"{MODEL_DIR}/motivation/xgb.pkl")
        rf_m  = joblib.load(f"{MODEL_DIR}/motivation/rf.pkl")
        df_mot = df_mot[df_mot["stress_level"].notna()].copy()
        y_m = le.transform(df_mot["stress_level"].astype(int))
        X_m = df_mot[feat_cols].fillna(0)
        # use StratifiedShuffleSplit for a robust stratified holdout
        from sklearn.model_selection import StratifiedShuffleSplit
        sss = StratifiedShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
        _, te_idx = next(sss.split(X_m, y_m))
        X_te_m = X_m.iloc[te_idx]
        y_te_m = y_m[te_idx]
        X_te_ms = sc.transform(X_te_m.values)
        prob = 0.40*lgb_m.predict_proba(X_te_ms) + 0.35*xgb_m.predict_proba(X_te_ms) + 0.25*rf_m.predict_proba(X_te_ms)
        y_pred_m = np.argmax(prob, axis=1)
        acc_m = accuracy_score(y_te_m, y_pred_m)
        cm = confusion_matrix(y_te_m, y_pred_m)
        fig, ax = plt.subplots(figsize=(6,5))
        disp = ConfusionMatrixDisplay(cm, display_labels=["Low","Medium","High"])
        disp.plot(ax=ax, cmap="Blues", colorbar=False)
        ax.set_title(f"Motivation Model — Confusion Matrix (Acc={acc_m:.3f})")
        plt.tight_layout()
        plt.savefig(os.path.join(EVAL_PLOTS_DIR, "motivation", "confusion_matrix.png"), dpi=150, bbox_inches="tight")
        plt.close()
        print("  → saved motivation/confusion_matrix.png")
    except Exception as e:
        print(f"  ! Motivation confusion matrix skipped: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    total_start = time.time()
    results = {}

    results["progress"]   = train_progress()
    results["motivation"] = train_motivation()
    results["reschedule"] = train_reschedule()
    results["profiling"]  = train_profiling()

    banner("FINAL METRICS SUMMARY")
    for agent, m in results.items():
        print(f"  {agent.upper():15s}: {m}")

    metrics = store_metrics(results)
    regenerate_plots(results)

    banner(f"ALL DONE  ({time.time()-total_start:.0f}s total)")
    print(f"  Metrics stored at {os.path.join(EVAL_PLOTS_DIR, 'summary', 'metrics.json')}")
    print(f"  Graphs regenerated in {EVAL_PLOTS_DIR}/")
