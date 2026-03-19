import pandas as pd
import numpy as np
import os
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler
import joblib
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--sample-size', type=int, default=100000)
parser.add_argument('--n-iter', type=int, default=30)
parser.add_argument('--random-state', type=int, default=42)
parser.add_argument('--log-target', action='store_true')
args = parser.parse_args()

PATH = 'backend/data/final_training/reschedule_training.csv'
SAMPLE = args.sample_size

print('Loading sample...')
reader = pd.read_csv(PATH, parse_dates=['timestamp','next_ts'], chunksize=200000)
chunks = []
for chunk in reader:
    if len(chunk) <= SAMPLE:
        chunks.append(chunk)
    else:
        chunks.append(chunk.sample(min(len(chunk), SAMPLE)))

df = pd.concat(chunks, ignore_index=True)
if len(df) > SAMPLE:
    df = df.sample(SAMPLE, random_state=args.random_state).reset_index(drop=True)

# Ensure numeric target
df['delta_s'] = pd.to_numeric(df['delta_s'], errors='coerce')
print('Initial rows:', len(df))

# Basic FE: q_freq, u_freq
df['q_freq'] = df['question_id'].map(df['question_id'].value_counts())
df['u_freq'] = df['user_id'].map(df['user_id'].value_counts())

# time features
if 'timestamp' in df.columns:
    df['hour'] = df['timestamp'].dt.hour
    df['dow'] = df['timestamp'].dt.dayofweek
else:
    df['hour'] = 0
    df['dow'] = 0

# Flag long gaps
df['is_long_gap'] = (df['delta_s'] > 86400).astype(int)

# Train/test split BEFORE computing train-based user aggregates to avoid leakage
train_df, test_df = train_test_split(df, test_size=0.2, random_state=args.random_state)

# Per-user aggregates computed on train only
user_stats = train_df.groupby('user_id')['delta_s'].agg(['count','mean','std']).rename(columns={'count':'u_count','mean':'u_mean_delta','std':'u_std_delta'})
train_df = train_df.join(user_stats, on='user_id')
test_df = test_df.join(user_stats, on='user_id')
# fill missing user stats in test with global train stats
for col in ['u_count','u_mean_delta','u_std_delta']:
    test_df[col] = test_df[col].fillna(train_df[col].median())
    train_df[col] = train_df[col].fillna(train_df[col].median())

FEATURES = ['correct','q_freq','u_freq','hour','dow','u_count','u_mean_delta','u_std_delta','is_long_gap']
for c in FEATURES:
    if c not in train_df.columns:
        train_df[c] = 0
        test_df[c] = 0

X_train = train_df[FEATURES].astype(float)
X_test = test_df[FEATURES].astype(float)

y_train = train_df['delta_s'].values
y_test = test_df['delta_s'].values

if args.log_target:
    print('Applying log1p transform to target')
    y_train = np.log1p(y_train)
    y_test = np.log1p(y_test)

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s = scaler.transform(X_test)

print('Searching hyperparameters for RandomForest...')
param_dist = {
    'n_estimators': [100, 200, 400, 800],
    'max_depth': [None, 6, 10, 20],
    'min_samples_split': [2,5,10],
    'min_samples_leaf': [1,2,4]
}
rf = RandomForestRegressor(random_state=args.random_state, n_jobs=-1)
search = RandomizedSearchCV(rf, param_distributions=param_dist, n_iter=args.n_iter, cv=3, scoring='neg_mean_squared_error', random_state=args.random_state, n_jobs=1, verbose=1)
search.fit(X_train_s, y_train)

best = search.best_estimator_
print('Best params:', search.best_params_)

# Predict and invert transform if needed
y_pred = best.predict(X_test_s)
if args.log_target:
    y_pred_inv = np.expm1(y_pred)
    y_test_inv = np.expm1(y_test)
else:
    y_pred_inv = y_pred
    y_test_inv = y_test

mse = mean_squared_error(y_test_inv, y_pred_inv)
rmse = np.sqrt(mse)
mae = mean_absolute_error(y_test_inv, y_pred_inv)
r2 = r2_score(y_test_inv, y_pred_inv)
print('Results on test: MSE', mse, 'RMSE', rmse, 'MAE', mae, 'R2', r2)

# Save model + scaler
out_dir = 'backend/app/ml/reschedule'
os.makedirs(out_dir, exist_ok=True)
model_path = os.path.join(out_dir, 'rf_fe_best.pkl')
scaler_path = os.path.join(out_dir, 'scaler_fe.pkl')
joblib.dump(best, model_path)
joblib.dump(scaler, scaler_path)
print('Saved model to', model_path)
print('Saved scaler to', scaler_path)
