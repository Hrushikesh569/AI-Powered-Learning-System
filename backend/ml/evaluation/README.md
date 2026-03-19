Evaluation utilities
====================

This folder contains utilities to evaluate ML models and agents and log
metrics/artifacts to MLflow.

Quickstart
----------

1. Ensure `mlflow` is available and optionally run `mlflow ui --backend-store-uri mlruns`.
2. From project root run a quick synthetic agent evaluation:

```bash
python backend/ml/evaluation/runner.py --agent schedule --runs 100 --state-dim 8
```

3. Start MLflow UI to inspect runs and artifacts:

```bash
mlflow ui --backend-store-uri mlruns
```

Extending
---------

- Use `Evaluator` for classification/regression/RL logging in your training scripts.
- The runner is a lightweight example — replace the random state generator with
  real test episodes or a streaming hook from production.
