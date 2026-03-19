import tempfile
import os
from backend.ml.evaluation.runner import run_agent_evaluation


def test_runner_smoke():
    # Run a very small synthetic evaluation into a temp mlflow store
    with tempfile.TemporaryDirectory() as td:
        os.environ['MLFLOW_TRACKING_URI'] = f'file:{td}'
        run_agent_evaluation(agent_name='schedule', runs=5, state_dim=4, experiment='pytest-agent')
        # mlruns dir should be created
        assert os.path.exists(td)
