import os
import io
import tempfile
from typing import Optional, Sequence, Iterable

import mlflow
import os
try:
    import wandb
    _WANDB_AVAILABLE = True
except Exception:
    _WANDB_AVAILABLE = False
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
try:
    import seaborn as sns
except Exception:
    sns = None
from sklearn import metrics


class Evaluator:
    def __init__(self, experiment_name: Optional[str] = None, tracking_uri: Optional[str] = None):
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        if experiment_name:
            mlflow.set_experiment(experiment_name)
        # optional Weights & Biases integration
        self.wandb_enabled = os.getenv('ENABLE_WANDB', 'false').lower() in ('1', 'true') and _WANDB_AVAILABLE
        if self.wandb_enabled:
            # initialize wandb run lazily during log calls
            self._wandb_run = None

    def _log_artifact_figure(self, fig, name: str):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        fig.tight_layout()
        fig.savefig(tmp.name)
        mlflow.log_artifact(tmp.name, artifact_path="plots")
        tmp.close()
        try:
            os.remove(tmp.name)
        except Exception:
            pass

        if self.wandb_enabled:
            try:
                if self._wandb_run is None:
                    self._wandb_run = wandb.init(reinit=True)
                wandb.log({f"plots/{name}": wandb.Image(tmp.name)})
            except Exception:
                pass

    def log_classification(self, y_true: Sequence, y_proba: Optional[Sequence] = None, y_pred: Optional[Sequence] = None, prefix: str = "cls"):
        y_true = np.array(y_true)
        if y_pred is None and y_proba is not None:
            if np.array(y_proba).ndim == 1:
                y_pred = (np.array(y_proba) >= 0.5).astype(int)
            else:
                y_pred = np.argmax(y_proba, axis=1)
        y_pred = np.array(y_pred)

        # Basic metrics
        acc = float(metrics.accuracy_score(y_true, y_pred))
        prec = float(metrics.precision_score(y_true, y_pred, average="weighted", zero_division=0))
        rec = float(metrics.recall_score(y_true, y_pred, average="weighted", zero_division=0))
        f1 = float(metrics.f1_score(y_true, y_pred, average="weighted", zero_division=0))

        mlflow.log_metric(f"{prefix}_accuracy", acc)
        mlflow.log_metric(f"{prefix}_precision", prec)
        mlflow.log_metric(f"{prefix}_recall", rec)
        mlflow.log_metric(f"{prefix}_f1", f1)

        # Confusion matrix plot
        try:
            labels = np.unique(np.concatenate([y_true, y_pred]))
            cm = metrics.confusion_matrix(y_true, y_pred, labels=labels)
            fig, ax = plt.subplots(figsize=(6, 5))
            sns.heatmap(cm, annot=True, fmt="d", ax=ax, cmap="Blues")
            ax.set_xlabel("Predicted")
            ax.set_ylabel("Actual")
            self._log_artifact_figure(fig, "confusion_matrix.png")
            plt.close(fig)
        except Exception:
            pass

        # ROC / PR for binary
        if y_proba is not None:
            y_proba = np.array(y_proba)
            if y_proba.ndim == 1 or y_proba.shape[1] == 2:
                # binary
                if y_proba.ndim == 2:
                    pos = y_proba[:, 1]
                else:
                    pos = y_proba
                try:
                    fpr, tpr, _ = metrics.roc_curve(y_true, pos)
                    roc_auc = float(metrics.auc(fpr, tpr))
                    mlflow.log_metric(f"{prefix}_roc_auc", roc_auc)
                    fig, ax = plt.subplots()
                    ax.plot(fpr, tpr, label=f"AUC={roc_auc:.3f}")
                    ax.plot([0, 1], [0, 1], linestyle="--", color="gray")
                    ax.set_xlabel("FPR")
                    ax.set_ylabel("TPR")
                    ax.set_title("ROC")
                    ax.legend()
                    self._log_artifact_figure(fig, "roc.png")
                    plt.close(fig)
                except Exception:
                    pass

                try:
                    precision, recall, _ = metrics.precision_recall_curve(y_true, pos)
                    ap = float(metrics.average_precision_score(y_true, pos))
                    mlflow.log_metric(f"{prefix}_average_precision", ap)
                    fig, ax = plt.subplots()
                    ax.plot(recall, precision)
                    ax.set_xlabel("Recall")
                    ax.set_ylabel("Precision")
                    ax.set_title("Precision-Recall")
                    self._log_artifact_figure(fig, "pr.png")
                    plt.close(fig)
                except Exception:
                    pass

    def log_regression(self, y_true: Sequence, y_pred: Sequence, prefix: str = "reg"):
        y_true = np.array(y_true)
        y_pred = np.array(y_pred)
        mse = float(metrics.mean_squared_error(y_true, y_pred))
        rmse = float(np.sqrt(mse))
        mae = float(metrics.mean_absolute_error(y_true, y_pred))
        r2 = float(metrics.r2_score(y_true, y_pred))
        mlflow.log_metric(f"{prefix}_mse", mse)
        mlflow.log_metric(f"{prefix}_rmse", rmse)
        mlflow.log_metric(f"{prefix}_mae", mae)
        mlflow.log_metric(f"{prefix}_r2", r2)

        try:
            fig, ax = plt.subplots()
            ax.scatter(y_true, y_pred, alpha=0.6)
            lims = [np.min([y_true, y_pred]), np.max([y_true, y_pred])]
            ax.plot(lims, lims, linestyle='--', color='gray')
            ax.set_xlabel('Actual')
            ax.set_ylabel('Predicted')
            self._log_artifact_figure(fig, 'reg_scatter.png')
            plt.close(fig)
        except Exception:
            pass

    def log_rl(self, episode_rewards: Iterable[float], prefix: str = "rl"):
        rewards = np.array(list(episode_rewards))
        mean_r = float(np.mean(rewards))
        median_r = float(np.median(rewards))
        std_r = float(np.std(rewards))
        total_r = float(np.sum(rewards))
        mlflow.log_metric(f"{prefix}_mean_reward", mean_r)
        mlflow.log_metric(f"{prefix}_median_reward", median_r)
        mlflow.log_metric(f"{prefix}_std_reward", std_r)
        mlflow.log_metric(f"{prefix}_total_reward", total_r)

        try:
            fig, ax = plt.subplots()
            ax.plot(rewards, marker='o')
            ax.set_xlabel('Episode')
            ax.set_ylabel('Reward')
            ax.set_title('Episode Rewards')
            self._log_artifact_figure(fig, 'episode_rewards.png')
            plt.close(fig)
        except Exception:
            pass

    def log_extra_metrics(self, metrics: dict, prefix: str = "custom"):
        """Log additional scalar metrics (from custom agent evaluators)."""
        if not metrics:
            return
        for k, v in metrics.items():
            try:
                mlflow.log_metric(f"{prefix}_{k}", float(v))
            except Exception:
                try:
                    mlflow.log_param(f"{prefix}_{k}", str(v))
                except Exception:
                    pass

        # also push to wandb if enabled
        if self.wandb_enabled:
            try:
                if self._wandb_run is None:
                    self._wandb_run = wandb.init(reinit=True)
                wandb.log({f"{prefix}/{k}": v for k, v in metrics.items()})
            except Exception:
                pass

    def stream_evaluate(self, generator: Iterable[dict], prefix: str = "stream"):
        """Consume a generator yielding dicts that may contain 'reward', 'y_true','y_pred','y_proba'.

        Each item is logged to MLflow as a metric at its step index.
        """
        for step, item in enumerate(generator):
            if 'reward' in item:
                mlflow.log_metric(f"{prefix}_reward", float(item['reward']), step=step)
            if 'y_true' in item and 'y_pred' in item:
                try:
                    acc = float(metrics.accuracy_score(item['y_true'], item['y_pred']))
                    mlflow.log_metric(f"{prefix}_acc", acc, step=step)
                except Exception:
                    pass
