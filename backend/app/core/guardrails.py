"""
Guardrails for ML and API safety.
- Input validation
- Output validation
- Bias/fairness checks
- Explainability hooks (SHAP)
- Adversarial input detection
"""
from fastapi import HTTPException
import numpy as np

def validate_ml_input(X, expected_shape):
    if not isinstance(X, np.ndarray) or X.shape[1] != expected_shape:
        raise HTTPException(status_code=400, detail="Invalid input shape for ML model.")

def validate_ml_output(y, allowed_range=None):
    if allowed_range and not (allowed_range[0] <= y <= allowed_range[1]):
        raise HTTPException(status_code=500, detail="ML output out of allowed range.")

def check_bias_fairness(model, X, y):
    # Placeholder for fairness/bias checks
    pass

def explain_with_shap(model, X):
    # Placeholder for SHAP explainability
    pass

def detect_adversarial_input(X):
    # Placeholder for adversarial input detection
    pass
