"""Progress feature importance & SHAP analysis.
Saves SHAP summary plot or permutation importances and top features JSON.
"""
import os
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.inspection import permutation_importance
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.join(os.path.dirname(__file__), "..")
import sys
sys.path.insert(0, ROOT)
TRAINING_DIR = os.path.join(ROOT, "data", "final_training")
MODEL_DIR = os.path.join(ROOT, "app", "ml")
EVAL_DIR = os.path.join(ROOT, "app", "evaluation_plots", "progress")
os.makedirs(EVAL_DIR, exist_ok=True)

# import the feature engineering helper from retrain script
from retrain_high_accuracy import _fe_progress

print("Loading data (sample)...")
df = pd.read_csv(os.path.join(TRAINING_DIR, "progress_training.csv"), nrows=50000)
X, y, users, questions = _fe_progress(df)

# load model and cont_cols
lgb_path = os.path.join(MODEL_DIR, "progress", "lgb_model.pkl")
cont_path = os.path.join(MODEL_DIR, "progress", "cont_cols.pkl")
if not os.path.exists(lgb_path):
    raise FileNotFoundError(lgb_path)

lgb_m = joblib.load(lgb_path)
cont_cols = joblib.load(cont_path)

# ensure columns
for c in cont_cols:
    if c not in X.columns:
        X[c] = 0
X = X.reindex(columns=cont_cols)

# make a user-holdout test
gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
_, test_idx = next(gss.split(X, y, groups=users))
X_te = X.iloc[test_idx]
y_te = y.iloc[test_idx]

results = {"method": None, "top_features": []}

# try SHAP first
try:
    import shap
    print("Running SHAP TreeExplainer...")
    expl = shap.TreeExplainer(lgb_m)
    # shap can be heavy; sample 5000 rows if large
    sample = X_te.sample(n=min(5000, len(X_te)), random_state=42)
    shap_vals = expl.shap_values(sample)
    # for binary classifier shap_values is list [neg, pos] -> take pos
    if isinstance(shap_vals, list) and len(shap_vals) >= 2:
        sv = np.abs(shap_vals[1]).mean(axis=0)
    else:
        sv = np.abs(shap_vals).mean(axis=0)
    feat_imps = dict(zip(sample.columns, sv.tolist()))
    top = sorted(feat_imps.items(), key=lambda x: x[1], reverse=True)[:50]
    results['method'] = 'shap'
    results['top_features'] = [{"feature": f, "mean_abs_shap": float(v)} for f, v in top]

    # save summary plot
    try:
        plt.figure(figsize=(6,8))
        shap.summary_plot(shap_vals, sample, show=False, plot_type='bar')
        plt.tight_layout()
        plt.savefig(os.path.join(EVAL_DIR, 'shap_bar.png'), dpi=150)
        plt.close()
        # summary dot plot
        shap.summary_plot(shap_vals, sample, show=False)
        plt.tight_layout()
        plt.savefig(os.path.join(EVAL_DIR, 'shap_summary.png'), dpi=150)
        plt.close()
        print('SHAP plots saved')
    except Exception as e:
        print('SHAP plotting failed:', e)

except Exception as e:
    print('SHAP unavailable or failed:', e)
    print('Falling back to permutation importance...')
    results['method'] = 'permutation'
    try:
        pi = permutation_importance(lgb_m, X_te, y_te, n_repeats=10, random_state=42, n_jobs=-1)
        imp_means = pi.importances_mean
        feat_imps = dict(zip(X_te.columns, imp_means))
        top = sorted(feat_imps.items(), key=lambda x: x[1], reverse=True)[:50]
        results['top_features'] = [{"feature": f, "perm_importance": float(v)} for f, v in top]
        # plot
        feats, vals = zip(*top[:20])
        plt.figure(figsize=(8,6))
        plt.barh(feats[::-1], vals[::-1], color='#3B82F6')
        plt.title('Top 20 Permutation Importances (Progress)')
        plt.tight_layout()
        plt.savefig(os.path.join(EVAL_DIR, 'perm_importance.png'), dpi=150)
        plt.close()
        print('Permutation importance plot saved')
    except Exception as e2:
        print('Permutation importance failed:', e2)

# save top features json
with open(os.path.join(EVAL_DIR, 'top_features.json'), 'w') as f:
    json.dump(results, f, indent=2)
print('Top features written to', os.path.join(EVAL_DIR, 'top_features.json'))
print('Done')
