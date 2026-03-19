"""Create tag TF-IDF + SVD embeddings and append to progress_training.csv, then retrain Progress.
"""
import os
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FINAL = os.path.join(ROOT, 'final_training')
PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

os.makedirs(FINAL, exist_ok=True)

print('Loading progress training...')
df = pd.read_csv(os.path.join(FINAL, 'progress_training.csv'))
# ensure tags column is string
if 'tags' not in df.columns:
    print('No tags column found; aborting tag embedding step')
else:
    tags = df['tags'].fillna('').astype(str)
    # replace spaces in tag lists to maintain tokens
    tags_text = tags.apply(lambda s: ' '.join(s.split()))
    vec = TfidfVectorizer(max_features=1024, token_pattern=r"\S+")
    X_tfidf = vec.fit_transform(tags_text)
    print('TF-IDF shape', X_tfidf.shape)
    n_comp = 16
    svd = TruncatedSVD(n_components=n_comp, random_state=42)
    X_svd = svd.fit_transform(X_tfidf)
    for i in range(n_comp):
        df[f'tag_svd_{i}'] = X_svd[:, i]
    out_path = os.path.join(FINAL, 'progress_training_augmented.csv')
    df.to_csv(out_path, index=False)
    print('Wrote augmented progress file:', out_path)

# Now call retrain Progress using augmented file by temporarily symlinking
import shutil
orig = os.path.join(FINAL, 'progress_training.csv')
aug = os.path.join(FINAL, 'progress_training_augmented.csv')
backup = os.path.join(FINAL, 'progress_training.backup.csv')
if os.path.exists(aug):
    print('Backing up original progress_training.csv')
    shutil.copy2(orig, backup)
    shutil.copy2(aug, orig)
    print('Replaced progress_training.csv with augmented version')
    # run retrain for progress only
    print('Running progress retrain...')
    os.chdir(os.path.join(PROJ_ROOT, 'backend'))
    rc = os.system(os.path.join(PROJ_ROOT, 'backend', 'venv', 'Scripts', 'python.exe') + ' run_progress_only.py')
    print('Retrain exit code', rc)
    # restore original
    shutil.copy2(backup, orig)
    print('Restored original progress_training.csv')
else:
    print('Augmented file missing; skipping retrain')
