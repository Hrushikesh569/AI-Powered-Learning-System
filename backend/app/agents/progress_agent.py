# Progress Monitoring Agent
# Predicts next academic performance, detects decline
import joblib
import numpy as np


class DummyRegressor:
    def predict(self, X):
        return np.zeros(X.shape[0])


class DummyAnomaly:
    def predict(self, X):
        return np.ones(X.shape[0])  # no anomaly


class DummyScaler:
    def transform(self, X):
        return X


class ProgressAgent:
    def __init__(self, rf_path='ml/progress/rf.pkl', xgb_path='ml/progress/xgb.pkl', iso_path='ml/progress/iso.pkl', scaler_path='ml/progress/scaler.pkl'):
        try:
            self.rf = joblib.load(rf_path)
        except Exception:
            self.rf = DummyRegressor()
        try:
            self.xgb = joblib.load(xgb_path)
        except Exception:
            self.xgb = DummyRegressor()
        try:
            self.iso = joblib.load(iso_path)
        except Exception:
            self.iso = DummyAnomaly()
        try:
            self.scaler = joblib.load(scaler_path)
        except Exception:
            self.scaler = DummyScaler()

    def predict(self, features, method='rf'):
        X = self.scaler.transform(np.array([features]))
        if method == 'rf':
            pred = self.rf.predict(X)[0]
        else:
            pred = self.xgb.predict(X)[0]
        risk = int(self.iso.predict(X)[0] == -1)
        return float(pred), risk
