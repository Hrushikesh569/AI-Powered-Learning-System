"""Simple runner to evaluate agents and log to MLflow using Evaluator.

This is an example CLI you can run from the project root to evaluate an
agent with synthetic inputs and see metrics/artifacts in MLflow (mlruns/).
"""
import sys
import os
import argparse
import numpy as np

# Ensure backend package is importable when running from repo root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.agents.schedule_agent import ScheduleAgent
from app.agents.reschedule_agent import RescheduleAgent
from ml.evaluation.evaluator import Evaluator
from ml.evaluation import custom_metrics
import mlflow


def _dummy_reward(action):
    """Simple reward: negative L2 norm of action (encourage small adjustments)."""
    a = np.array(action)
    return -float(np.linalg.norm(a))


def run_agent_evaluation(agent_name: str = 'schedule', runs: int = 50, state_dim: int = 8, experiment: str = 'agent-eval'):
    """Run a synthetic evaluation for the named agent and log metrics/artifacts to MLflow.

    This uses random gaussian states and a simple reward function. It also calls
    any agent-specific metric function defined in `custom_metrics`.
    """
    if agent_name == 'schedule':
        agent = ScheduleAgent()
        method = 'generate'
    elif agent_name == 'reschedule':
        agent = RescheduleAgent()
        method = 'adapt'
    else:
        raise ValueError('Unsupported agent')

    states = []
    actions = []
    rewards = []

    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name=f"{agent_name}-synthetic"):
        for i in range(runs):
            state = np.random.randn(state_dim).tolist()
            if method == 'generate':
                action = agent.generate(state)
                reward = _dummy_reward(action)
            else:
                # adapt-style agents may require a reward input; use placeholder
                reward = float(np.random.randn())
                action = agent.adapt(state, reward)
                reward = _dummy_reward(action)

            rewards.append(reward)
            actions.append(action)
            states.append(state)

            # stream logging per-step
            mlflow.log_metric('step_reward', reward, step=i)

        # final logging
        evaluator = Evaluator()
        evaluator.log_rl(rewards, prefix=agent_name)

        # run custom agent metrics if available
        try:
            metric_fn = getattr(custom_metrics, f"{agent_name}_metrics", None)
            if callable(metric_fn):
                extra = metric_fn(states, actions, rewards)
                evaluator.log_extra_metrics(extra, prefix=agent_name)
        except Exception:
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent', choices=['schedule', 'reschedule'], default='schedule')
    parser.add_argument('--runs', type=int, default=50)
    parser.add_argument('--state-dim', type=int, default=8)
    parser.add_argument('--experiment', type=str, default='agent-eval')
    args = parser.parse_args()
    run_agent_evaluation(agent_name=args.agent, runs=args.runs, state_dim=args.state_dim, experiment=args.experiment)
