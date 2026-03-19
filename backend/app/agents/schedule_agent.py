# Learning Schedule Generator Agent (RL)
# Generates personalized weekly study schedule

import numpy as np
import joblib


class DummyModel:
    def predict(self, X):
        # Return a zero-action vector matching input dim
        return [np.zeros(X.shape[1])]


class DummyScaler:
    def transform(self, X):
        return X


class ScheduleAgent:
    def __init__(self, policy_path='ml/schedule/dqn_policy.pt', scaler_path='ml/schedule/scaler.pkl'):
        try:
            self.policy = joblib.load(policy_path)
        except Exception:
            self.policy = DummyModel()
        try:
            self.scaler = joblib.load(scaler_path)
        except Exception:
            self.scaler = DummyScaler()

    def generate(self, state):
        X = self.scaler.transform(np.array([state]))
        action = self.policy.predict(X)
        return action[0].tolist()
