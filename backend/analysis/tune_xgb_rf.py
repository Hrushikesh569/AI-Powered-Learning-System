"""Optuna tuning for XGBoost and RandomForest for Progress task."""
import os
import sys
import json
import time
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))
import retrain_high_accuracy as ra
import optuna
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier

TRAIN = os.path.join(ra.TRAINING_DIR, 'progress_training.csv')
OUT_DIR = os.path.join(ra.MODEL_DIR, 'progress')
os.makedirs(OUT_DIR, exist_ok=True)

def tune_xgb(n_trials=48):
    df = pd.read_csv(TRAIN)
    X, y, users, questions = ra._fe_progress(df)
    groups = users.values

    def objective(trial):
        params = {
            'n_estimators': trial.suggest_categorical('n_estimators', [500, 1000, 1500]),
            'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.1, log=True),
            'max_depth': trial.suggest_int('max_depth', 3, 9),
            'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'gamma': trial.suggest_float('gamma', 0.0, 1.0),
            'random_state': 42,
            'n_jobs': -1,
            'verbosity': 0,
            'use_label_encoder': False,
            'eval_metric': 'logloss'
        }
        gss = GroupShuffleSplit(n_splits=3, test_size=0.20, random_state=42)
        aucs = []
        for tr_idx, val_idx in gss.split(X, y, groups=groups):
            X_tr, X_val = X.iloc[tr_idx], X.iloc[val_idx]
            y_tr, y_val = y.iloc[tr_idx], y.iloc[val_idx]
            if y_tr.nunique() < 2 or y_val.nunique() < 2:
                continue
            m = xgb.XGBClassifier(**params)
            try:
                # some XGBoost versions don't accept early_stopping_rounds in sklearn wrapper
                m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
                p = m.predict_proba(X_val)[:, 1]
                aucs.append(roc_auc_score(y_val, p))
            except Exception:
                continue
        return float(np.mean(aucs)) if len(aucs) else 0.0

    study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials)
    best = study.best_trial.params
    with open(os.path.join(OUT_DIR, 'xgb_optuna_params.json'), 'w') as f:
        json.dump(best, f, indent=2)
    # train final xgb on user split
    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    tr_idx, te_idx = next(gss.split(X, y, groups=users))
    X_tr, X_te = X.iloc[tr_idx], X.iloc[te_idx]
    y_tr, y_te = y.iloc[tr_idx], y.iloc[te_idx]
    params = best.copy(); params.update({'random_state':42, 'n_jobs':-1, 'verbosity':0, 'use_label_encoder': False, 'eval_metric':'logloss'})
    m = xgb.XGBClassifier(**params)
    m.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
    joblib.dump(m, os.path.join(OUT_DIR, 'xgb_optuna.pkl'), compress=3)
    auc = roc_auc_score(y_te, m.predict_proba(X_te)[:,1])
    return {'xgb_auc': float(auc), 'xgb_params': best}

def tune_rf(n_trials=32):
    df = pd.read_csv(TRAIN)
    X, y, users, questions = ra._fe_progress(df)
    groups = users.values

    def objective(trial):
        params = {
            'n_estimators': trial.suggest_categorical('n_estimators', [200, 300, 500]),
            'max_depth': trial.suggest_int('max_depth', 5, 50),
            'min_samples_leaf': trial.suggest_int('min_samples_leaf', 1, 10),
            'max_features': trial.suggest_categorical('max_features', ['sqrt', 'log2', 0.5]),
            'random_state': 42,
            'n_jobs': -1,
        }
        gss = GroupShuffleSplit(n_splits=3, test_size=0.20, random_state=42)
        aucs = []
        for tr_idx, val_idx in gss.split(X, y, groups=groups):
            X_tr, X_val = X.iloc[tr_idx], X.iloc[val_idx]
            y_tr, y_val = y.iloc[tr_idx], y.iloc[val_idx]
            if y_tr.nunique() < 2 or y_val.nunique() < 2:
                continue
            m = RandomForestClassifier(**params)
            try:
                m.fit(X_tr, y_tr)
                p = m.predict_proba(X_val)[:,1]
                aucs.append(roc_auc_score(y_val, p))
            except Exception:
                continue
        return float(np.mean(aucs)) if len(aucs) else 0.0

    study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials)
    best = study.best_trial.params
    with open(os.path.join(OUT_DIR, 'rf_optuna_params.json'), 'w') as f:
        json.dump(best, f, indent=2)
    # train final rf on user split
    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    tr_idx, te_idx = next(gss.split(X, y, groups=users))
    X_tr, X_te = X.iloc[tr_idx], X.iloc[te_idx]
    y_tr, y_te = y.iloc[tr_idx], y.iloc[te_idx]
    params = best.copy(); params.update({'random_state':42, 'n_jobs': -1})
    # ensure numeric max_features if it's 0.5
    if params.get('max_features') == 0.5:
        params['max_features'] = 0.5
    m = RandomForestClassifier(**params)
    m.fit(X_tr, y_tr)
    joblib.dump(m, os.path.join(OUT_DIR, 'rf_optuna.pkl'), compress=3)
    auc = roc_auc_score(y_te, m.predict_proba(X_te)[:,1])
    return {'rf_auc': float(auc), 'rf_params': best}

if __name__ == '__main__':
    start = time.time()
    out = {}
    print('Tuning XGBoost...')
    out.update(tune_xgb(n_trials=48))
    print('Tuning RandomForest...')
    out.update(tune_rf(n_trials=32))
    print('Done tuning. Results:')
    print(out)
    print('Total time:', time.time()-start)
