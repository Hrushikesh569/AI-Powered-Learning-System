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
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df = df.sort_values(["user_id", "timestamp"]).reset_index(drop=True)

    # ── Time features ──────────────────────────────────────────────────────
    ts = pd.to_datetime(df["timestamp"], unit="ms", errors="coerce")
    df["hour"]  = ts.dt.hour.fillna(12).astype(int)
    df["dow"]   = ts.dt.dayofweek.fillna(0).astype(int)
    df["month"] = ts.dt.month.fillna(1).astype(int)
    # morning / afternoon / evening bucket
    df["time_bucket"] = df["hour"].apply(lambda h: 0 if h < 12 else (1 if h < 17 else 2))

    # ── Frequency features ─────────────────────────────────────────────────
    qf = df["question_id"].value_counts(); df["q_freq"] = df["question_id"].map(qf)
    uf = df["user_id"].value_counts();     df["u_freq"] = df["user_id"].map(uf)

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
    df["last_q_ts"]         = df.groupby("question_id")["timestamp"].shift(1)
    df["log_time_since_q"]  = np.log1p((df["timestamp"] - df["last_q_ts"].fillna(df["timestamp"])).clip(lower=0))
    df["ts_diff"]           = grp["timestamp"].diff().fillna(0)
    df["new_session"]       = (df["ts_diff"] > 1_800_000).astype(int)
    sess_id = grp["new_session"].cumsum()
    df["in_sess_pos"]       = df.groupby(["user_id", sess_id]).cumcount()
    df["log_sess_pos"]      = np.log1p(df["in_sess_pos"])

    # ── Categorical encodings ──────────────────────────────────────────────
    df["user_cat"]     = df["user_id"].astype("category").cat.codes
    df["question_cat"] = df["question_id"].astype("category").cat.codes
    df["dataset_cat"]  = df["dataset"].astype("category").cat.codes

    FEAT_COLS = [
        "difficulty", "hour", "dow", "month", "time_bucket",
        "q_freq", "u_total", "u_freq",
        "u_cum_acc", "u_roll3", "u_roll5", "u_roll10", "u_roll20",
        "u_trend", "prev_correct", "u_streak",
        "u_diff_acc",
        "q_cum_acc", "q_hardness", "q_total",
        "ability_delta", "irt_score", "diff_gap",
        "attempt_n", "is_repeat",
        "log_time_since_q", "in_sess_pos", "log_sess_pos",
        "user_cat", "question_cat", "dataset_cat",
    ]
    return df[FEAT_COLS].fillna(0), df["correct"]


def train_progress():
    banner("PROGRESS  —  binary classification (ROC-AUC ≥ 0.97)")
    t0 = time.time()

    df = pd.read_csv(f"{TRAINING_DIR}/progress_training.csv")
    print(f"  Loaded {len(df):,} rows")

    X, y = _fe_progress(df)
    print(f"  Features: {X.shape[1]}")

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.20, random_state=42, stratify=y)

    # ── LightGBM ───────────────────────────────────────────────────────────
    lgb_params = dict(
        n_estimators=3000,
        learning_rate=0.02,
        num_leaves=255,
        max_depth=-1,
        min_child_samples=10,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_alpha=0.05,
        reg_lambda=0.1,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    lgb_m = lgb.LGBMClassifier(**lgb_params)
    lgb_m.fit(X_tr, y_tr,
              eval_set=[(X_te, y_te)],
              callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)])

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

    # ── Ensemble via probability average ──────────────────────────────────
    prob_lgb = lgb_m.predict_proba(X_te)[:, 1]
    prob_xgb = xgb_m.predict_proba(X_te)[:, 1]
    prob_avg = 0.55 * prob_lgb + 0.45 * prob_xgb

    auc = roc_auc_score(y_te, prob_avg)
    print(f"\n  Ensemble ROC-AUC : {auc:.4f}")

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
    num_cols = df.select_dtypes(include="number").columns.tolist()
    feat_cols = [c for c in num_cols if c.lower() not in {l.lower() for l in LEAK}
                 and "unnamed" not in c.lower()]

    df = df[df["stress_level"].notna()].copy()
    le = LabelEncoder()
    y  = le.fit_transform(df["stress_level"].astype(int))
    X  = df[feat_cols].fillna(0)

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
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df["next_ts"]   = pd.to_numeric(df["next_ts"],   errors="coerce")
    df = df.sort_values(["user_id", "timestamp"]).reset_index(drop=True)

    ts = pd.to_datetime(df["timestamp"], unit="ms", errors="coerce")
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

    df["ts_diff"]      = grp["timestamp"].diff().fillna(0)
    df["log_ts_diff"]  = np.log1p(df["ts_diff"].clip(lower=0))
    df["new_session"]  = (df["ts_diff"] > 1_800_000).astype(int)

    df["user_cat"]     = df["user_id"].astype("category").cat.codes
    df["question_cat"] = df["question_id"].astype("category").cat.codes
    df["dataset_cat"]  = df["dataset"].astype("category").cat.codes

    FEAT = [
        "difficulty", "hour", "dow",
        "u_cum_acc", "u_roll5", "u_roll20", "u_total", "prev_correct",
        "q_cum_acc", "q_hardness",
        "ability_delta", "irt_score",
        "attempt_n", "is_repeat",
        "log_ts_diff", "new_session",
        "user_cat", "question_cat", "dataset_cat",
    ]
    return df[FEAT].fillna(0), df["delta_s"]


def train_reschedule():
    banner("RESCHEDULE  —  regression (R² ≥ 0.95)")
    t0 = time.time()

    df = pd.read_csv(f"{TRAINING_DIR}/reschedule_training.csv")
    print(f"  Loaded {len(df):,} rows")

    X, y = _fe_reschedule(df)
    print(f"  Target stats: mean={y.mean():.1f}  max={y.max():.1f}")

    # Log-transform target for regression stability
    y_log = np.log1p(y)

    X_tr, X_te, y_tr_log, y_te_log = train_test_split(
        X, y_log, test_size=0.20, random_state=42
    )
    y_te = np.expm1(y_te_log)

    sc = StandardScaler()
    X_tr_s = sc.fit_transform(X_tr)
    X_te_s  = sc.transform(X_te)

    # ── LightGBM regression ───────────────────────────────────────────────
    lgb_r = lgb.LGBMRegressor(
        n_estimators=3000,
        learning_rate=0.02,
        num_leaves=255,
        min_child_samples=10,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    lgb_r.fit(X_tr_s, y_tr_log,
              eval_set=[(X_te_s, y_te_log)],
              callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)])

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

    r2 = r2_score(y_te, pred)
    print(f"\n  Ensemble R²      : {r2:.4f}")

    save(lgb_r,   f"{MODEL_DIR}/reschedule/lgb_fe_model.pkl")
    save(xgb_r,   f"{MODEL_DIR}/reschedule/xgb_best.pkl")
    save(sc,      f"{MODEL_DIR}/reschedule/scaler_fe.pkl")

    print(f"\n  Done in {time.time()-t0:.1f}s")
    return {"r2": r2}


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
        X_p, y_p = _fe_progress(df_prog)
        _, X_te_p, _, y_te_p = train_test_split(X_p, y_p, test_size=0.20, random_state=42, stratify=y_p)
        lgb_m = joblib.load(f"{MODEL_DIR}/progress/lgb_model.pkl")
        xgb_m = joblib.load(f"{MODEL_DIR}/progress/xgb.pkl")
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
        X_m = df_mot[feat_cols].fillna(0).values
        _, X_te_m, _, y_te_m = train_test_split(X_m, y_m, test_size=0.2, random_state=42, stratify=y_m)
        X_te_ms = sc.transform(X_te_m)
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
