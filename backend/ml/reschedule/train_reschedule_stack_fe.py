import pandas as pd
import numpy as np
import os
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import StackingRegressor
import joblib
import argparse

try:
    from catboost import CatBoostRegressor
    HAS_CAT = True
except Exception:
    HAS_CAT = False

parser = argparse.ArgumentParser()
parser.add_argument('--sample-size', type=int, default=100000)
parser.add_argument('--random-state', type=int, default=42)
parser.add_argument('--use-cat', action='store_true')
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

# FE
df['delta_s'] = pd.to_numeric(df['delta_s'], errors='coerce')
df['q_freq'] = df['question_id'].map(df['question_id'].value_counts())
df['u_freq'] = df['user_id'].map(df['user_id'].value_counts())
if 'timestamp' in df.columns:
    df['hour'] = df['timestamp'].dt.hour
    df['dow'] = df['timestamp'].dt.dayofweek
else:
    df['hour'] = 0
    df['dow'] = 0

# long gap
df['is_long_gap'] = (df['delta_s'] > 86400).astype(int)

train_df, test_df = train_test_split(df, test_size=0.2, random_state=args.random_state)
user_stats = train_df.groupby('user_id')['delta_s'].agg(['count','mean','std']).rename(columns={'count':'u_count','mean':'u_mean_delta','std':'u_std_delta'})
train_df = train_df.join(user_stats, on='user_id')
test_df = test_df.join(user_stats, on='user_id')
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

y_train = np.log1p(train_df['delta_s'].values)
y_test = np.log1p(test_df['delta_s'].values)

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s = scaler.transform(X_test)

estimators = []
rf = RandomForestRegressor(n_estimators=400, max_depth=10, min_samples_split=10, min_samples_leaf=2, random_state=args.random_state, n_jobs=-1)
estimators.append(('rf', rf))
if args.use_cat and HAS_CAT:
    print('Adding CatBoost to ensemble')
    cb = CatBoostRegressor(iterations=500, depth=6, learning_rate=0.05, verbose=0)
    estimators.append(('cat', cb))
else:
    print('CatBoost not used or not available')

stack = StackingRegressor(estimators=estimators, final_estimator=RidgeCV(), n_jobs=1, passthrough=False)
print('Fitting stacking regressor...')
stack.fit(X_train_s, y_train)

pred = stack.predict(X_test_s)
pred_inv = np.expm1(pred)
y_test_inv = np.expm1(y_test)

mse = mean_squared_error(y_test_inv, pred_inv)
rmse = np.sqrt(mse)
mae = mean_absolute_error(y_test_inv, pred_inv)
r2 = r2_score(y_test_inv, pred_inv)
print('Stack results: MSE', mse, 'RMSE', rmse, 'MAE', mae, 'R2', r2)

out_dir = 'backend/app/ml/reschedule'
os.makedirs(out_dir, exist_ok=True)
joblib.dump(stack, os.path.join(out_dir, 'stack_fe_model.pkl'))
joblib.dump(scaler, os.path.join(out_dir, 'scaler_fe.pkl'))
print('Saved stack model and scaler')
