import os
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'data', 'final_training', 'progress_training.csv')
MODEL_DIR = os.path.join(ROOT, 'app', 'ml', 'progress')
OUT_PATH = os.path.join(MODEL_DIR, 'ensemble_weights.json')

def load_models():
    lgb_m = joblib.load(os.path.join(MODEL_DIR, 'lgb_model.pkl'))
    xgb_m = joblib.load(os.path.join(MODEL_DIR, 'xgb.pkl'))
    meta = None
    try:
        meta = joblib.load(os.path.join(MODEL_DIR, 'meta_clf.pkl'))
    except Exception:
        meta = None
    return lgb_m, xgb_m, meta

def main():
    import sys
    # ensure backend dir is on path so we can import retrain_high_accuracy
    sys.path.insert(0, ROOT)
    from retrain_high_accuracy import _fe_progress
    print('Loading data...')
    df = pd.read_csv(DATA)
    X, y, users, questions = _fe_progress(df)

    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    tr_idx, te_idx = next(gss.split(X, y, groups=users))
    X_tr, X_te = X.iloc[tr_idx].copy(), X.iloc[te_idx].copy()
    y_tr, y_te = y.iloc[tr_idx], y.iloc[te_idx]

    # load models
    lgb_m, xgb_m, meta_clf = load_models()

    # remove duplicate column names (keep first occurrence) to match training behavior
    if X_tr.columns.duplicated().any():
        X_tr = X_tr.loc[:, ~X_tr.columns.duplicated()]
    if X_te.columns.duplicated().any():
        X_te = X_te.loc[:, ~X_te.columns.duplicated()]

    # Align feature columns to what the LightGBM model expects
    try:
        model_feat = lgb_m.booster_.feature_name()
        # Add any missing columns with zeros and drop extras
        for c in model_feat:
            if c not in X_tr.columns:
                X_tr[c] = 0
            if c not in X_te.columns:
                X_te[c] = 0
        # Ensure order matches the model's feature list
        X_tr = X_tr[model_feat]
        X_te = X_te[model_feat]
        print('Model expects', len(model_feat), 'features; X_tr/X_te now have', X_tr.shape[1], X_te.shape[1])
        print('Model feature sample:', model_feat[:30])
        print('X_tr columns sample:', list(X_tr.columns)[:30])
        extra = [c for c in X_te.columns if c not in set(model_feat)]
        missing = [c for c in model_feat if c not in set(X_te.columns)]
        print('Extra columns after align (should be empty):', extra[:10])
        print('Missing columns after align (should be empty):', missing[:10])
    except Exception:
        # fallback to cont_cols if available
        cont_path = os.path.join(MODEL_DIR, 'cont_cols.pkl')
        if os.path.exists(cont_path):
            cont_cols = joblib.load(cont_path)
            for c in cont_cols:
                if c not in X_tr.columns:
                    X_tr[c] = 0
                if c not in X_te.columns:
                    X_te[c] = 0
            X_tr = X_tr[cont_cols]
            X_te = X_te[cont_cols]
        else:
            print('Warning: could not align features to model; proceeding with current features')

    # train a quick RF on training fold
    print('Training quick RandomForest baseline...')
    rf = RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=42)
    rf.fit(X_tr, y_tr)

    # get probabilities
    print('Collecting probabilities...')
    p_l = lgb_m.predict_proba(X_te)[:, 1]
    p_x = xgb_m.predict_proba(X_te)[:, 1]
    p_r = rf.predict_proba(X_te)[:, 1]

    best = {'auc': 0.0, 'weights': None}
    # random search over convex weights
    n_iter = 5000
    rng = np.random.RandomState(123)
    for i in range(n_iter):
        w = rng.rand(3)
        w = w / w.sum()
        p = w[0]*p_l + w[1]*p_x + w[2]*p_r
        try:
            auc = roc_auc_score(y_te, p)
        except Exception:
            auc = 0.0
        if auc > best['auc']:
            best = {'auc': float(auc), 'weights': [float(w[0]), float(w[1]), float(w[2])]}

    # evaluate meta classifier if present
    meta_auc = None
    if meta_clf is not None:
        try:
            probs_meta = meta_clf.predict_proba(np.vstack([p_l, p_x, p_r]).T)[:, 1]
            meta_auc = float(roc_auc_score(y_te, probs_meta))
        except Exception:
            meta_auc = None

    print('Best random-search AUC:', best['auc'], 'weights lgb/xgb/rf =', best['weights'])
    if meta_auc is not None:
        print('Meta classifier AUC:', meta_auc)

    out = {'best_search': best, 'meta_auc': meta_auc}
    with open(OUT_PATH, 'w') as f:
        json.dump(out, f, indent=2)
    print('Saved ensemble weights to', OUT_PATH)

if __name__ == '__main__':
    main()
