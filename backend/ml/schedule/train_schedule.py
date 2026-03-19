"""
Train and save a mock RL policy for the Schedule Generator Agent.
Replace with real RL training as needed.
"""
import os
import numpy as np
import joblib
import mlflow
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor

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


df = _load_csv('progress_training.csv')
if df is None or df.empty:
	print('No schedule-related data found — falling back to random sample')
	import numpy as np
	X = np.random.rand(200, 6)
	y = np.random.rand(200, 5)
else:
	# reuse progress features; create a multi-output target if possible
	numeric = df.select_dtypes('number')
	if numeric.shape[1] >= 6:
		X = numeric.iloc[:, :6]
	else:
		X = numeric
	# target: try to find next-slot columns or multiple action columns
	candidate_targets = [c for c in numeric.columns if any(k in c.lower() for k in ('action', 'slot', 'next'))]
	if candidate_targets and len(candidate_targets) >= 1:
		y = numeric[candidate_targets].iloc[:, :5]
	else:
		# if no multi-target available, derive simple targets from numeric columns
		if numeric.shape[1] >= 5:
			y = numeric.iloc[:, :5]
		else:
			import numpy as np
			y = np.random.rand(len(X), 5)

scaler = StandardScaler().fit(X)
X_scaled = scaler.transform(X)

import numpy as _np
if hasattr(y, 'ndim') and getattr(y, 'ndim') == 1:
	y = _np.asarray(y).reshape(-1, 1)

rf_policy = RandomForestRegressor().fit(X_scaled, y)

os.makedirs('backend/app/ml/schedule', exist_ok=True)
joblib.dump(scaler, 'backend/app/ml/schedule/scaler.pkl')
joblib.dump(rf_policy, 'backend/app/ml/schedule/dqn_policy.pt')

with mlflow.start_run(run_name='train_schedule'):
	try:
		score = rf_policy.score(X_scaled, y)
		mlflow.log_metric('train_score', float(score))
	except Exception:
		pass
	mlflow.log_artifact('backend/app/ml/schedule/scaler.pkl')
	mlflow.log_artifact('backend/app/ml/schedule/dqn_policy.pt')

print('Schedule policy trained, saved, and logged to MLflow.')
