"""Optuna-based hyperparameter tuner for Progress and Reschedule models.

Usage:
    python backend/optuna_tune.py --trials 24 --task both

This script uses the feature engineers in `retrain_high_accuracy.py` and performs
lightweight CV-based optimization for LightGBM parameters, then trains a final
model with the best params and saves artifacts into the same model folders.
"""

import os
import sys
import json
import time
import argparse

# allow importing retrain_high_accuracy from same folder
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import retrain_high_accuracy as ra

try:
    import optuna
except Exception as e:
    print("Optuna is not installed. Install with `pip install optuna` and retry.")
    raise

import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.metrics import roc_auc_score, r2_score
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb


def tune_progress(n_trials=24):
    print("\nStarting Optuna tuning: Progress (binary, ROC-AUC)")
    df = pd.read_csv(f"{ra.TRAINING_DIR}/progress_training.csv")
    X, y, users, questions = ra._fe_progress(df)

    groups = users.values

    def objective(trial):
        params = {
            'n_estimators': trial.suggest_categorical('n_estimators', [500, 1000, 1500, 2000]),
            'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.05, log=True),
            'num_leaves': trial.suggest_categorical('num_leaves', [31, 63, 127, 255]),
            'min_child_samples': trial.suggest_int('min_child_samples', 5, 50, step=5),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'reg_alpha': trial.suggest_float('reg_alpha', 0.0, 0.5),
            'reg_lambda': trial.suggest_float('reg_lambda', 0.0, 1.0),
            'random_state': 42,
            'n_jobs': -1,
            'verbosity': -1,
        }
        # Use repeated GroupShuffleSplit to ensure folds contain both classes
        from sklearn.model_selection import GroupShuffleSplit
        n_repeats = 3
        aucs = []
        gss = GroupShuffleSplit(n_splits=n_repeats, test_size=0.20, random_state=42)
        for tr_idx, val_idx in gss.split(X, y, groups=groups):
            X_tr_cv, X_val_cv = X.iloc[tr_idx], X.iloc[val_idx]
            y_tr_cv, y_val_cv = y.iloc[tr_idx], y.iloc[val_idx]
            # ensure both classes present in train and val
            if y_tr_cv.nunique() < 2 or y_val_cv.nunique() < 2:
                continue
            model = lgb.LGBMClassifier(**params)
            try:
                model.fit(X_tr_cv, y_tr_cv, eval_set=[(X_val_cv, y_val_cv)], early_stopping_rounds=30, verbose=False)
                prob = model.predict_proba(X_val_cv)[:, 1]
                aucs.append(roc_auc_score(y_val_cv, prob))
            except Exception:
                continue
        if len(aucs) == 0:
            return 0.0
        return float(np.mean(aucs))

    study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    print("Best trial:", study.best_trial.value)
    print(study.best_trial.params)
    # save params
    os.makedirs(os.path.join(ra.MODEL_DIR, 'progress'), exist_ok=True)
    with open(os.path.join(ra.MODEL_DIR, 'progress', 'optuna_best_params.json'), 'w') as f:
        json.dump(study.best_trial.params, f, indent=2)

    # Train final model with best params using user-level train/test split
    print("Training final Progress LGB with best params...")
    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    train_idx, test_idx = next(gss.split(X, y, groups=users))
    X_tr, X_te = X.iloc[train_idx], X.iloc[test_idx]
    y_tr, y_te = y.iloc[train_idx], y.iloc[test_idx]

    best_params = study.best_trial.params.copy()
    best_params.update({'random_state': 42, 'n_jobs': -1, 'verbosity': -1})
    lgb_m = lgb.LGBMClassifier(**best_params)
    lgb_m.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], callbacks=[lgb.early_stopping(50, verbose=False)])

    # Save model and columns
    joblib.dump(lgb_m, os.path.join(ra.MODEL_DIR, 'progress', 'lgb_optuna.pkl'), compress=3)
    joblib.dump(list(X_tr.columns), os.path.join(ra.MODEL_DIR, 'progress', 'cont_cols_optuna.pkl'))
    sc = StandardScaler().fit(X_tr)
    joblib.dump(sc, os.path.join(ra.MODEL_DIR, 'progress', 'scaler_optuna.pkl'))

    prob = lgb_m.predict_proba(X_te)[:, 1]
    auc = roc_auc_score(y_te, prob)
    print(f"Final Progress LGB AUC = {auc:.4f}")
    return {'best_auc': float(auc), 'params': study.best_trial.params}


def tune_reschedule(n_trials=24):
    print("\nStarting Optuna tuning: Reschedule (regression, log R²)")
    df = pd.read_csv(f"{ra.TRAINING_DIR}/reschedule_training.csv")
    X, y, users = ra._fe_reschedule(df)
    y = y.fillna(0).astype(float)
    # clip at 99th pct
    cap = float(y.quantile(0.99))
    if np.isfinite(cap) and cap > 0:
        y_clipped = y.clip(upper=cap)
    else:
        y_clipped = y
    y_log = np.log1p(y_clipped)

    groups = users.values

    def objective(trial):
        params = {
            'n_estimators': trial.suggest_categorical('n_estimators', [500, 1000, 1500]),
            'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.05, log=True),
            'num_leaves': trial.suggest_categorical('num_leaves', [31, 63, 127]),
            'min_child_samples': trial.suggest_int('min_child_samples', 5, 30, step=5),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'random_state': 42,
            'n_jobs': -1,
            'verbosity': -1,
        }
        # Use repeated GroupShuffleSplit for robustness
        from sklearn.model_selection import GroupShuffleSplit
        n_repeats = 3
        r2s = []
        gss = GroupShuffleSplit(n_splits=n_repeats, test_size=0.20, random_state=42)
        for tr_idx, val_idx in gss.split(X, y_log, groups=groups):
            X_tr_cv, X_val_cv = X.iloc[tr_idx], X.iloc[val_idx]
            y_tr_cv, y_val_cv = y_log.iloc[tr_idx], y_log.iloc[val_idx]
            model = lgb.LGBMRegressor(**params)
            try:
                model.fit(X_tr_cv, y_tr_cv, eval_set=[(X_val_cv, y_val_cv)], early_stopping_rounds=30, verbose=False)
                pred = model.predict(X_val_cv)
                r2s.append(r2_score(y_val_cv, pred))
            except Exception:
                continue
        if len(r2s) == 0:
            return -999.0
        return float(np.mean(r2s))

    study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    print("Best trial:", study.best_trial.value)
    print(study.best_trial.params)
    os.makedirs(os.path.join(ra.MODEL_DIR, 'reschedule'), exist_ok=True)
    with open(os.path.join(ra.MODEL_DIR, 'reschedule', 'optuna_best_params.json'), 'w') as f:
        json.dump(study.best_trial.params, f, indent=2)

    # final training and save
    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    train_idx, test_idx = next(gss.split(X, y, groups=users))
    X_tr, X_te = X.iloc[train_idx], X.iloc[test_idx]
    y_tr_log, y_te_log = np.log1p(y_clipped.iloc[train_idx]), np.log1p(y_clipped.iloc[test_idx])
    y_te = y.iloc[test_idx]

    best_params = study.best_trial.params.copy()
    best_params.update({'random_state': 42, 'n_jobs': -1, 'verbosity': -1})
    lgb_r = lgb.LGBMRegressor(**best_params)
    lgb_r.fit(X_tr, y_tr_log, eval_set=[(X_te, y_te_log)], callbacks=[lgb.early_stopping(50, verbose=False)])

    joblib.dump(lgb_r, os.path.join(ra.MODEL_DIR, 'reschedule', 'lgb_optuna.pkl'), compress=3)
    sc = StandardScaler().fit(X_tr)
    joblib.dump(sc, os.path.join(ra.MODEL_DIR, 'reschedule', 'scaler_optuna.pkl'))

    pred_log = lgb_r.predict(X_te)
    pred = np.expm1(pred_log)
    r2_orig = r2_score(y_te, pred)
    r2_log = r2_score(np.log1p(y_te), pred_log)
    print(f"Final Reschedule: R² log = {r2_log:.4f}, R² orig = {r2_orig:.4f}")
    return {'r2_log': float(r2_log), 'r2_orig': float(r2_orig), 'params': study.best_trial.params}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--trials', type=int, default=24, help='Number of Optuna trials per task')
    parser.add_argument('--task', choices=['progress', 'reschedule', 'both'], default='both')
    args = parser.parse_args()

    start = time.time()
    results = {}
    if args.task in ('progress', 'both'):
        results['progress'] = tune_progress(n_trials=args.trials)
    if args.task in ('reschedule', 'both'):
        results['reschedule'] = tune_reschedule(n_trials=args.trials)

    print('\nDone. Results:')
    print(json.dumps(results, indent=2))
    print(f'Total time: {time.time()-start:.1f}s')
