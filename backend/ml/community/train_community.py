"""
Train and save models for Community Agent (PCA as embedding, Scaler).
Replace mock data with real data loading as needed.
"""
import numpy as np
import joblib
import mlflow
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

# TODO: Replace with real data loading from backend/data/
X = np.random.rand(200, 6)

scaler = StandardScaler().fit(X)
X_scaled = scaler.transform(X)

pca = PCA(n_components=3).fit(X_scaled)

joblib.dump(scaler, 'scaler.pkl')
joblib.dump(pca, 'embedding.pkl')

with mlflow.start_run(run_name='train_community'):
	mlflow.log_metric('explained_variance', float(sum(pca.explained_variance_ratio_)))
	mlflow.log_artifact('scaler.pkl')
	mlflow.log_artifact('embedding.pkl')

print('Community models trained, saved, and logged to MLflow.')
