# Feedback & Motivation Agent
# Classifies motivation, recommends intervention
import joblib
import numpy as np


class DummyClassifier:
    def predict(self, X):
        return np.zeros(X.shape[0])


class DummyScaler:
    def transform(self, X):
        return X


class MotivationAgent:
    def __init__(self, rf_path='ml/motivation/rf.pkl', xgb_path='ml/motivation/xgb.pkl', scaler_path='ml/motivation/scaler.pkl'):
        try:
            self.rf = joblib.load(rf_path)
        except Exception:
            self.rf = DummyClassifier()
        try:
            self.xgb = joblib.load(xgb_path)
        except Exception:
            self.xgb = DummyClassifier()
        try:
            self.scaler = joblib.load(scaler_path)
        except Exception:
            self.scaler = DummyScaler()

    def classify(self, features, method='rf'):
        X = self.scaler.transform(np.array([features]))
        if method == 'rf':
            pred = self.rf.predict(X)[0]
        else:
            pred = self.xgb.predict(X)[0]
        intervention = self._get_intervention(pred)
        return int(pred), intervention

    def _get_intervention(self, category):
        # Map category to intervention template
        interventions = {0: 'Take a short break', 1: 'Try group study', 2: 'Use visual aids'}
        return interventions.get(category, 'Stay motivated!')
