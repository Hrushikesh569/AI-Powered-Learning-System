# Adaptive Rescheduling Agent (RL)
# Triggers on performance drop/stress/missed milestones
try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    torch = None
    _TORCH_AVAILABLE = False
import numpy as np
import joblib


class DummyPolicy:
    def __call__(self, x):
        return np.zeros((1, 1))


class DummyScaler:
    def transform(self, X):
        return X


class RescheduleAgent:
    def __init__(self, policy_path='ml/reschedule/dqn_policy.pt', scaler_path='ml/reschedule/scaler.pkl'):
        if _TORCH_AVAILABLE:
            try:
                self.policy = torch.jit.load(policy_path)
                self._use_torch = True
            except Exception:
                self.policy = DummyPolicy()
                self._use_torch = False
        else:
            self.policy = DummyPolicy()
            self._use_torch = False
        try:
            self.scaler = joblib.load(scaler_path)
        except Exception:
            self.scaler = DummyScaler()

    def adapt(self, state, reward):
        X = self.scaler.transform(np.array([state]))
        if self._use_torch and _TORCH_AVAILABLE:
            with torch.no_grad():
                new_action = self.policy(torch.tensor(X, dtype=torch.float32)).numpy()
        else:
            new_action = self.policy(X)
        return np.array(new_action).flatten().tolist()
