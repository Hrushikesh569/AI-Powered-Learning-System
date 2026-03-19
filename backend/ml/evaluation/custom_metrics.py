"""Agent-specific custom evaluation metrics.

Each function accepts the collected `states`, `actions`, `rewards` lists from
an evaluation run and returns a dict of custom scalar metrics and optionally
artifact-producing data.

Naming convention: `<agent_name>_metrics(states, actions, rewards) -> dict`.
"""
import numpy as np


def schedule_metrics(states, actions, rewards):
    """Custom metrics for the ScheduleAgent.

    - `stability`: inverse of mean step-to-step action change (higher is better)
    - `coverage`: fraction of time slots that are non-zero across actions
    - returns dict of metric_name: value
    """
    arr = np.array(actions)
    if arr.size == 0:
        return {}

    # stability: 1 / (1 + mean L2 diff between consecutive actions)
    if arr.shape[0] > 1:
        diffs = np.linalg.norm(np.diff(arr, axis=0), axis=1)
        mean_diff = float(np.mean(diffs))
    else:
        mean_diff = 0.0
    stability = 1.0 / (1.0 + mean_diff)

    # coverage: fraction of action dimensions that are non-zero on average
    coverage = float((np.abs(arr) > 1e-6).mean())

    return {
        'schedule_stability': float(stability),
        'schedule_coverage': float(coverage),
        'schedule_mean_reward': float(np.mean(rewards)) if len(rewards) else 0.0,
    }


def reschedule_metrics(states, actions, rewards):
    """Custom metrics for the RescheduleAgent.

    - `responsiveness`: average magnitude of action change following negative reward
    - `recovery_rate`: fraction episodes where reward improved after action
    """
    arr = np.array(actions)
    r = np.array(rewards)
    if arr.size == 0:
        return {}

    responsiveness = 0.0
    recovery_count = 0
    total = 0
    for i in range(1, len(r)):
        if r[i-1] < 0:
            change = np.linalg.norm(arr[i] - arr[i-1])
            responsiveness += change
            total += 1
            if r[i] > r[i-1]:
                recovery_count += 1
    responsiveness = float(responsiveness / total) if total > 0 else 0.0
    recovery_rate = float(recovery_count / total) if total > 0 else 0.0

    return {
        'reschedule_responsiveness': responsiveness,
        'reschedule_recovery_rate': recovery_rate,
        'reschedule_mean_reward': float(r.mean()) if len(r) else 0.0,
    }


def progress_metrics(states, actions, rewards):
    """Custom metrics for Progress Agent (monitoring predictions).

    - `consistency`: inverse std of rewards (higher means consistent performance)
    - `anomaly_count`: count of episodes with reward < threshold
    """
    r = np.array(rewards)
    if r.size == 0:
        return {}

    consistency = 1.0 / (1.0 + float(r.std()))
    anomaly_count = int((r < (r.mean() - 2 * r.std())).sum()) if r.size else 0

    return {
        'progress_consistency': float(consistency),
        'progress_anomaly_count': anomaly_count,
        'progress_mean_reward': float(r.mean()),
    }
