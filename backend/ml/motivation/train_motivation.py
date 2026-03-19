"""
Train and save models for Motivation Agent (RF, XGB, Scaler).
Replace mock data with real data loading as needed.
"""
import os
import joblib
import mlflow
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier


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


df = _load_csv('motivation_training.csv')
if df is None or df.empty:
	print('No motivation training data found — falling back to small random sample')
	import numpy as np
	X = np.random.rand(200, 6)
	y = np.random.randint(0, 3, 200)
else:
	# choose a categorical target if available
	cats = [c for c in df.columns if any(k in c.lower() for k in ('label', 'class', 'cat', 'motivate', 'stress'))]
	numeric = df.select_dtypes('number')
	if cats:
		ycol = cats[0]
		y = df[ycol]
		X = df.drop(columns=[ycol]).select_dtypes('number')
	else:
		# fallback: if there are few unique values in a numeric column, use it
		y = None
		for c in numeric.columns:
			if df[c].nunique() <= 10:
				y = df[c]
				break
		if y is None:
			if numeric.shape[1] >= 2:
				y = numeric.iloc[:, 0]
				X = numeric.iloc[:, 1:]
			else:
				import numpy as np
				X = np.random.rand(200, 6)
				y = np.random.randint(0, 3, 200)

scaler = StandardScaler().fit(X)
X_scaled = scaler.transform(X)

rf = RandomForestClassifier().fit(X_scaled, y)
xgb = XGBClassifier().fit(X_scaled, y)

os.makedirs('backend/app/ml/motivation', exist_ok=True)
joblib.dump(scaler, 'backend/app/ml/motivation/scaler.pkl')
joblib.dump(rf, 'backend/app/ml/motivation/rf.pkl')
joblib.dump(xgb, 'backend/app/ml/motivation/xgb.pkl')

with mlflow.start_run(run_name='train_motivation'):
	try:
		mlflow.log_metric('rf_accuracy', float(rf.score(X_scaled, y)))
	except Exception:
		pass
	try:
		mlflow.log_metric('xgb_accuracy', float(xgb.score(X_scaled, y)))
	except Exception:
		pass
	mlflow.log_artifact('backend/app/ml/motivation/scaler.pkl')
	mlflow.log_artifact('backend/app/ml/motivation/rf.pkl')
	mlflow.log_artifact('backend/app/ml/motivation/xgb.pkl')

print('Motivation models trained, saved, and logged to MLflow.')
