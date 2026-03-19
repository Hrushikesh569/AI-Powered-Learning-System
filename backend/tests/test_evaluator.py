import tempfile
import os
from backend.ml.evaluation.evaluator import Evaluator


def test_evaluator_regression_basic():
    with tempfile.TemporaryDirectory() as td:
        tracking = f"file:{td}"
        ev = Evaluator(experiment_name='test_exp', tracking_uri=tracking)
        y_true = [1.0, 2.0, 3.0]
        y_pred = [1.1, 1.9, 3.05]
        ev.log_regression(y_true, y_pred, prefix='treg')
        # Verify mlruns directory created
        assert os.path.exists(td)


def test_evaluator_rl_basic():
    with tempfile.TemporaryDirectory() as td:
        tracking = f"file:{td}"
        ev = Evaluator(experiment_name='test_exp', tracking_uri=tracking)
        ev.log_rl([1, 2, 3, 4], prefix='trl')
        assert os.path.exists(td)
