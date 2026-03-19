"""Fast LightGBM leaf-embedding (hashed leaves + SVD) and retrain Progress.
Designed to run quickly on large data by sampling for dimensionality reduction.
"""
import os
import sys
import numpy as np
import pandas as pd
from sklearn.feature_extraction import FeatureHasher
from sklearn.decomposition import TruncatedSVD
import lightgbm as lgb
from sklearn.model_selection import GroupShuffleSplit

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FINAL = os.path.join(ROOT, 'final_training')
AUG_PATH = os.path.join(FINAL, 'progress_training_leaf_augmented.csv')
ORIG_PATH = os.path.join(FINAL, 'progress_training.csv')
BACKUP_PATH = os.path.join(FINAL, 'progress_training.backup.csv')

# try to import feature engineering
import importlib.util
ra_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'retrain_high_accuracy.py'))
spec = importlib.util.spec_from_file_location('retrain_high_accuracy', ra_path)
ra = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ra)
_fe_progress = ra._fe_progress

print('Loading progress data (may be large) ...')
# prefer augmented tags file if exists
base_path = ORIG_PATH
if os.path.exists(os.path.join(FINAL, 'progress_training_augmented.csv')):
    base_path = os.path.join(FINAL, 'progress_training_augmented.csv')

df = pd.read_csv(base_path)
print('rows=', len(df))

# perform FE to get numeric matrix X
X_all, y_all, users_all, q_all = _fe_progress(df)

# user-group split
gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
train_idx, test_idx = next(gss.split(X_all, y_all, groups=users_all))
X_tr = X_all.iloc[train_idx]
X_te = X_all.iloc[test_idx]

y_tr = y_all.iloc[train_idx]

def train_small_lgb_get_leaves(X_tr, X_all):
    print('Training small LGB to get leaf indices...')
    # Ensure there are no duplicate column names (LightGBM errors on duplicates)
    if X_all.columns.duplicated().any():
        print('Warning: duplicate columns found in features. Dropping duplicate columns (keep first occurrence).')
        # keep first occurrence of each column name
        unique_cols = []
        seen = set()
        for c in X_all.columns:
            if c not in seen:
                seen.add(c)
                unique_cols.append(c)
        X_all = X_all[unique_cols]
        X_tr = X_tr[unique_cols]
        # debug: list duplicates and counts
        from collections import Counter
        cnt = Counter(list(unique_cols))
        dups = [k for k, v in cnt.items() if v > 1]
        if dups:
            print('Still duplicated after dedupe (unexpected):', dups)
        else:
            # but print if original had duplicates for visibility
            orig_cnt = Counter(list(pd.Series(X_all.columns)))
            dup_names = [k for k, v in orig_cnt.items() if v > 1]
            if dup_names:
                print('Dropped duplicate names:', dup_names)
    params = dict(n_estimators=200, learning_rate=0.05, num_leaves=31, random_state=42, n_jobs=-1, verbosity=-1)
    m = lgb.LGBMClassifier(**params)
    # Debug prints for duplicate feature name issues
    cols_tr = list(X_tr.columns)
    # show exact repr for columns named like 'part'
    occ = [i for i, c in enumerate(cols_tr) if str(c).strip() == 'part']
    if occ:
        print('Found "part"-like column at positions (0-based):', occ)
        for i in occ:
            print('col index', i, 'repr:', repr(cols_tr[i]))
    # fallback: ensure columns are unique by renaming duplicates with suffix
    if len(cols_tr) != len(set(cols_tr)):
        print('Renaming duplicate columns to ensure uniqueness for LightGBM')
        new_cols = []
        seen = {}
        for c in cols_tr:
            if c in seen:
                seen[c] += 1
                new_cols.append(f"{c}__dup{seen[c]}")
            else:
                seen[c] = 0
                new_cols.append(c)
        X_tr.columns = new_cols
        X_all.columns = new_cols
        cols_tr = new_cols
    m.fit(X_tr, y_tr)
    # get leaf indices for all rows
    leaves = m.booster_.predict(X_all, pred_leaf=True)
    return leaves

leaves = train_small_lgb_get_leaves(X_tr, X_all)
print('Leaves shape', np.array(leaves).shape)

# Convert leaf rows to hashed sparse vectors using FeatureHasher
from sklearn.feature_extraction import FeatureHasher
n_hash = 2048
hasher = FeatureHasher(n_features=n_hash, input_type='pair')

# Prepare iterable of token pairs per row: (token,1)
def gen_pairs(leaves_array):
    for row in leaves_array:
        # row is array of leaf indices per tree
        pairs = [(f't{i}_{int(v)}', 1) for i, v in enumerate(row)]
        yield pairs

print('Hashing leaves into fixed-size features...')
H = hasher.transform(gen_pairs(leaves))  # sparse matrix
print('Hashed shape', H.shape)

# Fit truncated SVD on a sample to reduce to 32 dims
n_comp = 32
sample_n = min(100000, H.shape[0])
print(f'Sampling {sample_n} rows to fit SVD...')
if sample_n < H.shape[0]:
    idx = np.random.RandomState(42).choice(H.shape[0], size=sample_n, replace=False)
    H_sample = H[idx]
else:
    H_sample = H

svd = TruncatedSVD(n_components=n_comp, random_state=42)
print('Fitting SVD...')
svd.fit(H_sample)
print('Transforming full hashed matrix...')
H_reduced = svd.transform(H)
print('Reduced shape', H_reduced.shape)

# append to original df as new columns
for i in range(n_comp):
    df[f'leaf_svd_{i}'] = H_reduced[:, i]

print('Writing augmented CSV...')
df.to_csv(AUG_PATH, index=False)
print('Augmented file saved:', AUG_PATH)

# swap files and retrain progress quickly
import shutil
import subprocess
print('Backing up original and swapping in augmented file...')
shutil.copy2(ORIG_PATH, BACKUP_PATH)
shutil.copy2(AUG_PATH, ORIG_PATH)

print('Running progress retrain using current Python executable...')
            # Use the same Python interpreter that's running this script to avoid venv path issues
cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
py = sys.executable
print('Python executable:', py)
run_script = os.path.abspath(os.path.join(cwd, 'backend', 'run_progress_only.py'))
print('Running script:', run_script, 'with cwd:', cwd)
try:
    result = subprocess.run([py, run_script], cwd=cwd, check=False)
    rc = result.returncode
except Exception as e:
    print('Retrain invocation failed:', e)
    rc = 2
print('Retrain exit code', rc)

# restore original
print('Restoring original progress file...')
shutil.copy2(BACKUP_PATH, ORIG_PATH)
print('Done')
