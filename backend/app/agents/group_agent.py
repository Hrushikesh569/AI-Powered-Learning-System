# Group Matching Agent
# Assigns optimal study groups
import joblib
import numpy as np


class DummyCluster:
    def predict(self, X):
        return np.zeros(X.shape[0], dtype=int)


class DummyScaler:
    def transform(self, X):
        return X


class GroupAgent:
    def __init__(self, clustering_path='ml/group/kmeans.pkl', scaler_path='ml/group/scaler.pkl'):
        try:
            self.kmeans = joblib.load(clustering_path)
        except Exception:
            self.kmeans = DummyCluster()
        try:
            self.scaler = joblib.load(scaler_path)
        except Exception:
            self.scaler = DummyScaler()

    def match(self, user_embeddings, constraints=None):
        X = self.scaler.transform(np.array(user_embeddings))
        labels = self.kmeans.predict(X)
        return labels.tolist()
