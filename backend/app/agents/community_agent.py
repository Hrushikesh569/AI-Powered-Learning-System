# Community Interaction Agent
# Models peer compatibility
import joblib
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


class DummyEmbedding:
    def transform(self, X):
        return X


class DummyScaler:
    def transform(self, X):
        return X


class CommunityAgent:
    def __init__(self, embedding_path='ml/community/embedding.pkl', scaler_path='ml/community/scaler.pkl'):
        try:
            self.embedding_model = joblib.load(embedding_path)
        except Exception:
            self.embedding_model = DummyEmbedding()
        try:
            self.scaler = joblib.load(scaler_path)
        except Exception:
            self.scaler = DummyScaler()

    def compatibility(self, user_features, peer_features):
        user_emb = self.embedding_model.transform(self.scaler.transform(np.array([user_features])))[0]
        peer_emb = self.embedding_model.transform(self.scaler.transform(np.array([peer_features])))[0]
        score = cosine_similarity([user_emb], [peer_emb])[0][0]
        return float(score)
