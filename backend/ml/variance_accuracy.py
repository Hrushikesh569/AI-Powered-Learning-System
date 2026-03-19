"""
variance_accuracy.py — Generate summary/variance_accuracy.png only.
Quick standalone script; run directly (no subprocess wrapper).

docker exec docker-backend-1 python /app/variance_accuracy.py
"""
import os, warnings, time
import numpy as np
import pandas as pd
import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import lightgbm as lgb

warnings.filterwarnings('ignore')

TRAINING_DIR = '/app/training_data'
OUT_DIR      = '/app/evaluation_plots/summary'

os.makedirs(OUT_DIR, exist_ok=True)
sns.set_theme(style='whitegrid', palette='muted', font_scale=1.1)

t0 = time.time()
print('Loading motivation CSV...')
csv_path = os.path.join(TRAINING_DIR, 'motivation_training.csv')
df = pd.read_csv(csv_path)
print(f'  Loaded: {df.shape}  ({time.time()-t0:.1f}s)')

# Identify target
if 'stress_level' not in df.columns:
    print('ERROR: stress_level column not found. Columns:', list(df.columns[:10]))
    raise SystemExit(1)

# Drop rows where target is NaN
df = df[df['stress_level'].notna()].copy()
df['stress_level'] = df['stress_level'].astype(int)
print(f'  After dropna on target: {len(df)} rows')

# Feature selection: numeric only, no leakage columns
LEAK = {'stress_level', 'Stress_Score', 'Stress_Level'}
num_cols = df.select_dtypes(include='number').columns.tolist()
feat_cols = [c for c in num_cols if c not in LEAK and 'unnamed' not in c.lower()]
print(f'  Features: {len(feat_cols)}')

X = df[feat_cols].fillna(0).values
y = LabelEncoder().fit_transform(df['stress_level'].values)
n_cls = len(np.unique(y))
print(f'  Classes: {n_cls}  |  X shape: {X.shape}')

X_tr, X_te, y_tr, y_te = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
sc = StandardScaler().fit(X_tr)
X_tr_s = sc.transform(X_tr)
X_te_s  = sc.transform(X_te)
print(f'  Train: {len(X_tr)}  Test: {len(X_te)}')

sizes  = [0.10, 0.25, 0.50, 0.75, 1.00]
res_rf  = []
res_lgb = []

for frac in sizes:
    n = max(50, int(len(X_tr) * frac))
    rng = np.random.RandomState(42)
    idx = rng.choice(len(X_tr), n, replace=False)
    Xs  = X_tr_s[idx]
    ys  = y_tr[idx]

    t = time.time()
    rf = RandomForestClassifier(
        n_estimators=30, max_depth=6, n_jobs=1, random_state=42
    ).fit(Xs, ys)
    acc_rf = accuracy_score(y_te, rf.predict(X_te_s))
    res_rf.append(acc_rf)

    params = {
        'objective':   'multiclass',
        'num_class':   n_cls,
        'num_leaves':  15,
        'num_iterations': 50,
        'verbose':    -1,
        'seed':        42,
    }
    ds = lgb.Dataset(Xs, label=ys, free_raw_data=True)
    bst = lgb.train(params, ds)
    acc_lgb = accuracy_score(y_te, np.argmax(bst.predict(X_te_s), axis=1))
    res_lgb.append(acc_lgb)

    elapsed = time.time() - t
    print(f'  frac={frac:.0%}  n={n:4d}  RF={acc_rf:.4f}  LGB={acc_lgb:.4f}  ({elapsed:.1f}s)')

sample_counts = [max(50, int(len(X_tr)*f)) for f in sizes]

fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(sample_counts, res_rf,  'o-', lw=2, label='Random Forest (n_est=30)')
ax.plot(sample_counts, res_lgb, 's-', lw=2, label='LightGBM (n_iter=50)')
ax.set_title('Accuracy vs Training Set Size — Motivation Agent',
             fontsize=14, fontweight='bold')
ax.set_xlabel('Training Samples')
ax.set_ylabel('Test Accuracy')
ax.legend()
ax.grid(True, alpha=0.3)

out_path = os.path.join(OUT_DIR, 'variance_accuracy.png')
plt.tight_layout()
plt.savefig(out_path, dpi=150, bbox_inches='tight')
plt.close()
print(f'\nSaved → {out_path}')
print(f'Total time: {time.time()-t0:.1f}s')
