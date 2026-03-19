"""
Train and save models for Progress Monitoring Agent (RF, XGB, IsolationForest, Scaler).
Replace mock data with real data loading as needed.
"""
import os
import joblib
import mlflow
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from xgboost import XGBRegressor


DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'final_training'))


def _load_csv(name):
	path = os.path.join(DATA_DIR, name)
	if not os.path.exists(path):
		return None
	size_mb = os.path.getsize(path) / (1024 * 1024)
	if size_mb > 200:
		print(f'Large {name} ({size_mb:.1f}MB) — sampling first 200k rows')
		return pd.read_csv(path, nrows=200000)
	return pd.read_csv(path)


def _choose_target(df):
	if df is None or df.empty:
		return None, None
	candidates = [c for c in df.columns if any(k in c.lower() for k in ('score', 'correct', 'outcome', 'delta', 'label', 'target'))]
	numeric = df.select_dtypes('number')
	if candidates:
		ycol = candidates[0]
	else:
		non_id = [c for c in numeric.columns if not any(k in c.lower() for k in ('user', 'id', 'timestamp'))]
		ycol = non_id[0] if non_id else None
	if ycol is None:
		return df.select_dtypes('number'), None
	X = df.drop(columns=[ycol])
	X = X.select_dtypes('number')
	y = df[ycol]
	return X, y


df = _load_csv('progress_training.csv')
if df is None or df.empty:
	print('No progress training data found — falling back to small random sample')
	import numpy as np
	X = np.random.rand(200, 6)
	y = np.random.rand(200)
else:
	X, y = _choose_target(df)
	if y is None:
		if X is None or X.empty:
			import numpy as np
			X = np.random.rand(200, 6)
			y = np.random.rand(200)
		else:
			y = X.iloc[:, 0]
			X = X.iloc[:, 1:]

scaler = StandardScaler().fit(X)
X_scaled = scaler.transform(X)

rf = RandomForestRegressor().fit(X_scaled, y)
xgb = XGBRegressor().fit(X_scaled, y)
iso = IsolationForest().fit(X_scaled)

os.makedirs('backend/app/ml/progress', exist_ok=True)
joblib.dump(scaler, 'backend/app/ml/progress/scaler.pkl')
joblib.dump(rf, 'backend/app/ml/progress/rf.pkl')
joblib.dump(xgb, 'backend/app/ml/progress/xgb.pkl')
joblib.dump(iso, 'backend/app/ml/progress/iso.pkl')

with mlflow.start_run(run_name='train_progress'):
	mlflow.log_metric('rf_score', float(rf.score(X_scaled, y)))
	try:
		mlflow.log_metric('xgb_score', float(xgb.score(X_scaled, y)))
	except Exception:
		pass
	mlflow.log_artifact('backend/app/ml/progress/scaler.pkl')
	mlflow.log_artifact('backend/app/ml/progress/rf.pkl')
	mlflow.log_artifact('backend/app/ml/progress/xgb.pkl')
	mlflow.log_artifact('backend/app/ml/progress/iso.pkl')

print('Progress models trained, saved, and logged to MLflow.')
