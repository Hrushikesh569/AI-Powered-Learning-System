"""Evaluation utilities for ML models and agents.

Expose Evaluator and a simple runner utility for logging metrics and plots
to MLflow and saving artifacts locally.
"""
from .evaluator import Evaluator
from .runner import run_agent_evaluation

__all__ = ["Evaluator", "run_agent_evaluation"]
