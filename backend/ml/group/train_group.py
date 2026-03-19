"""
Train and save models for Group Agent (KMeans, Scaler).
Replace mock data with real data loading as needed.
"""
import numpy as np
import joblib
import mlflow
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

# TODO: Replace with real data loading from backend/data/
X = np.random.rand(200, 6)

scaler = StandardScaler().fit(X)
X_scaled = scaler.transform(X)

kmeans = KMeans(n_clusters=4, random_state=42).fit(X_scaled)

joblib.dump(scaler, 'scaler.pkl')
joblib.dump(kmeans, 'kmeans.pkl')

with mlflow.start_run(run_name='train_group'):
	mlflow.log_metric('inertia', float(kmeans.inertia_))
	mlflow.log_artifact('scaler.pkl')
	mlflow.log_artifact('kmeans.pkl')

print('Group models trained, saved, and logged to MLflow.')
