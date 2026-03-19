import os
import json
import time
from datetime import datetime

ROOT = os.path.abspath(os.path.dirname(__file__))
OUT_DIR = os.path.join(ROOT, 'app', 'evaluation_plots', 'summary')
os.makedirs(OUT_DIR, exist_ok=True)
OUT_PATH = os.path.join(OUT_DIR, 'metrics.json')

def main():
    t0 = time.time()
    from retrain_high_accuracy import train_progress, train_reschedule, train_motivation, train_profiling
    metrics = {}

    print('Running Progress retrain...')
    try:
        prog = train_progress()
        metrics['progress'] = prog
    except Exception as e:
        metrics['progress'] = {'error': str(e)}

    print('Running Reschedule retrain...')
    try:
        res = train_reschedule()
        metrics['reschedule'] = res
    except Exception as e:
        metrics['reschedule'] = {'error': str(e)}

    print('Running Motivation retrain...')
    try:
        mot = train_motivation()
        metrics['motivation'] = mot
    except Exception as e:
        metrics['motivation'] = {'error': str(e)}

    print('Running Profiling retrain...')
    try:
        prof = train_profiling()
        metrics['profiling'] = prof
    except Exception as e:
        metrics['profiling'] = {'error': str(e)}

    metrics['timestamp'] = datetime.utcnow().isoformat() + 'Z'
    metrics['elapsed_s'] = time.time() - t0

    with open(OUT_PATH, 'w') as f:
        json.dump(metrics, f, indent=2)
    print('Saved metrics to', OUT_PATH)

    # Update README with short summary under a Machine Learning Metrics section
    rd = os.path.join(os.path.dirname(__file__), '..', 'README.md')
    try:
        with open(rd, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception:
        text = ''

    summary = '\n\n**Automated Retrain Metrics (' + metrics['timestamp'] + ')**\n'
    for k, v in metrics.items():
        if k in ('timestamp', 'elapsed_s'):
            continue
        summary += f'- **{k}**: {v}\n'

    if 'Machine Learning Metrics' in text:
        # append summary after header
        text = text.replace('**Machine Learning Metrics**', '**Machine Learning Metrics**' + summary)
    else:
        text = text + '\n\n**Machine Learning Metrics**' + summary

    with open(rd, 'w', encoding='utf-8') as f:
        f.write(text)
    print('Updated README.md with retrain summary')

if __name__ == '__main__':
    main()
