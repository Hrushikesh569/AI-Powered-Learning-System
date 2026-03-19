"""
Train and save models for User Profiling Agent (KMeans, GMM, Scaler).
Replace mock data with real data loading as needed.
"""
import os
import joblib
import mlflow
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture


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


df = _load_csv('profiling_training.csv')
if df is None or df.empty:
	print('No profiling training data found — falling back to small random sample')
	import numpy as np
	X = np.random.rand(200, 6)
else:
	X = df.select_dtypes('number')
	if X.empty:
		import numpy as np
		X = np.random.rand(200, 6)

scaler = StandardScaler().fit(X)
X_scaled = scaler.transform(X)

kmeans = KMeans(n_clusters=3, random_state=42).fit(X_scaled)
gmm = GaussianMixture(n_components=3, random_state=42).fit(X_scaled)

os.makedirs('backend/app/ml/profiling', exist_ok=True)
joblib.dump(scaler, 'backend/app/ml/profiling/scaler.pkl')
joblib.dump(kmeans, 'backend/app/ml/profiling/kmeans.pkl')
joblib.dump(gmm, 'backend/app/ml/profiling/gmm.pkl')

with mlflow.start_run(run_name='train_profiling'):
	mlflow.log_metric('kmeans_inertia', float(kmeans.inertia_))
	mlflow.log_artifact('backend/app/ml/profiling/scaler.pkl')
	mlflow.log_artifact('backend/app/ml/profiling/kmeans.pkl')
	mlflow.log_artifact('backend/app/ml/profiling/gmm.pkl')

print('Profiling models trained, saved, and logged to MLflow.')
