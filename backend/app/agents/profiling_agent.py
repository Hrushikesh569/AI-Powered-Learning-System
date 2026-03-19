"""User Profiling Agent

Clusters students into behavioral/academic personas.
This implementation is intentionally dummy-safe: it does not load
any external model files so that the backend can always start.
"""

import numpy as np


class DummyModel:
    def predict(self, X):
        # Always return cluster 0
        return [0]


class DummyScaler:
    def transform(self, X):
        # No-op scaling
        return X


class ProfilingAgent:
    def __init__(self, *_, **__):
        self.kmeans = DummyModel()
        self.gmm = DummyModel()
        self.scaler = DummyScaler()

    def predict(self, features, method: str = "kmeans") -> int:
        X = self.scaler.transform(np.array([features]))
        if method == "kmeans":
            label = self.kmeans.predict(X)[0]
        else:
            label = self.gmm.predict(X)[0]
        return int(label)
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    


def predict(self, features, method='kmeans'):
    X = self.scaler.transform(np.array([features]))
    if method == 'kmeans':
        label = self.kmeans.predict(X)[0]
    else:
        label = self.gmm.predict(X)[0]
    return int(label)
