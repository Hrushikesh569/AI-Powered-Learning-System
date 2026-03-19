import numpy as np
from backend.ml.evaluation.custom_metrics import schedule_metrics, reschedule_metrics, progress_metrics


def test_schedule_metrics_basic():
    states = [[0]] * 3
    actions = [[0.0, 1.0], [0.1, 0.9], [0.05, 0.95]]
    rewards = [1, 2, 3]
    m = schedule_metrics(states, actions, rewards)
    assert 'schedule_stability' in m
    assert 'schedule_coverage' in m


def test_reschedule_metrics_basic():
    states = [[0]] * 4
    actions = [[0], [0.5], [1.0], [0.2]]
    rewards = [-1, -0.5, 0.2, 1.0]
    m = reschedule_metrics(states, actions, rewards)
    assert 'reschedule_responsiveness' in m
    assert 'reschedule_recovery_rate' in m


def test_progress_metrics_basic():
    states = [[0]] * 5
    actions = [[0]] * 5
    rewards = [1, 1, 1, 1, 1]
    m = progress_metrics(states, actions, rewards)
    assert 'progress_consistency' in m
    assert 'progress_mean_reward' in m
