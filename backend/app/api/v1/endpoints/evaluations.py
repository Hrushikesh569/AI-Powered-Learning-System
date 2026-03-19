from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
from typing import List

try:
    import mlflow
    _MLFLOW_AVAILABLE = True
except ImportError:
    _MLFLOW_AVAILABLE = False

router = APIRouter()


def _require_mlflow():
    if not _MLFLOW_AVAILABLE:
        raise HTTPException(status_code=503, detail="MLflow is not installed. Add 'mlflow' to requirements.txt to enable evaluation tracking.")


@router.get("/runs")
def list_runs(experiment_name: str = None, max_results: int = 50):
    """List MLflow runs for an experiment (or all experiments if not provided)."""
    _require_mlflow()
    tracking_uri = os.getenv('MLFLOW_TRACKING_URI', None)
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    client = mlflow.tracking.MlflowClient()
    experiments = []
    if experiment_name:
        exp = client.get_experiment_by_name(experiment_name)
        if not exp:
            raise HTTPException(status_code=404, detail="Experiment not found")
        experiments = [exp.experiment_id]
    else:
        experiments = [e.experiment_id for e in client.list_experiments()]

    runs = []
    for exp_id in experiments:
        runs_resp = client.search_runs([exp_id], max_results=max_results)
        for r in runs_resp:
            # list artifacts for run
            art_list = []
            try:
                artifacts = client.list_artifacts(r.info.run_id)
                for a in artifacts:
                    art_list.append(a.path or a.path)
            except Exception:
                art_list = []

            runs.append({
                'run_id': r.info.run_id,
                'experiment_id': r.info.experiment_id,
                'start_time': r.info.start_time,
                'status': r.info.status,
                'metrics': r.data.metrics,
                'params': r.data.params,
                'artifacts': art_list,
            })
    return runs


@router.get('/artifact/{run_id}/{path:path}')
def get_artifact(run_id: str, path: str):
    """Return a file path to an artifact for a run."""
    _require_mlflow()
    tracking_uri = os.getenv('MLFLOW_TRACKING_URI', None)
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    client = mlflow.tracking.MlflowClient()
    try:
        local_path = client.download_artifacts(run_id, path)
        if not os.path.exists(local_path):
            raise FileNotFoundError(local_path)
        return FileResponse(local_path)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get('/metrics/{run_id}/{metric_key}')
def get_metric_history(run_id: str, metric_key: str):
    """Return time series for a given metric key for a run."""
    _require_mlflow()
    tracking_uri = os.getenv('MLFLOW_TRACKING_URI', None)
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    client = mlflow.tracking.MlflowClient()
    try:
        history = client.get_metric_history(run_id, metric_key)
        # history is a list of Metric objects with .timestamp and .value
        res = [{'timestamp': h.timestamp, 'value': h.value, 'step': getattr(h, 'step', None)} for h in history]
        return res
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
