"""
evaluate_all.py — Comprehensive evaluation + retrain script for all ML agents.
Run from backend directory:
    python ml/evaluate_all.py

Outputs:
  app/evaluation_plots/  — paper-quality PNGs (150 DPI)
  Re-saves fixed profiling + motivation models to app/ml/
"""
import os, sys, warnings, time
import numpy as np
import pandas as pd
import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns

from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture
from sklearn.decomposition import PCA
from sklearn.metrics import (
    accuracy_score, f1_score, confusion_matrix, roc_auc_score,
    roc_curve, precision_recall_curve, average_precision_score,
    mean_absolute_error, mean_squared_error, silhouette_score,
    classification_report, log_loss
)
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier, XGBRegressor
import lightgbm as lgb

warnings.filterwarnings('ignore')

TRAINING_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "final_training")
MODEL_DIR    = os.path.join(os.path.dirname(__file__), "..", "app", "ml")
OUT_DIR      = os.path.join(os.path.dirname(__file__), "..", "app", "evaluation_plots")
DPI          = 150

os.makedirs(OUT_DIR, exist_ok=True)
for sub in ('progress', 'motivation', 'profiling', 'reschedule', 'summary'):
    os.makedirs(os.path.join(OUT_DIR, sub), exist_ok=True)

sns.set_theme(style='whitegrid', palette='muted', font_scale=1.1)
COLORS = sns.color_palette('muted', 8)

print(f'\n{"="*60}')
print(' AI-Powered Learning System — Evaluation Report')
print(f'{"="*60}\n')

# ─────────────────────────────────────────────────────────────
# HELPER UTILITIES
# ─────────────────────────────────────────────────────────────

def savefig(fname, tight=True):
    path = os.path.join(OUT_DIR, fname)
    if tight:
        plt.tight_layout()
    plt.savefig(path, dpi=DPI, bbox_inches='tight')
    plt.close()
    print(f'  Saved → {path}')


def load_csv(name, nrows=None):
    path = os.path.join(TRAINING_DIR, name)
    if not os.path.exists(path):
        print(f'  [WARN] {name} not found at {path}')
        return None
    size_mb = os.path.getsize(path) / 1e6
    if size_mb > 200 and nrows is None:
        nrows = 200_000
        print(f'  Large {name} ({size_mb:.0f} MB) — sampling {nrows:,} rows')
    df = pd.read_csv(path, nrows=nrows)
    print(f'  Loaded {name}: {df.shape[0]:,} rows × {df.shape[1]} cols')
    return df


def save_metrics_row(store, agent, model, metrics_dict):
    store.append({'agent': agent, 'model': model, **metrics_dict})


# ─────────────────────────────────────────────────────────────
# 1. PROGRESS AGENT — LGB (22 engineered features)
# ─────────────────────────────────────────────────────────────
print('\n[1/4] PROGRESS AGENT ─────────────────────────────────')

all_metrics = []

def _fe_progress(df):
    """Replicate the 22-feature engineering pipeline for the progress LGB model."""
    df = df.copy()
    df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
    df = df.sort_values(['user_id', 'timestamp']).reset_index(drop=True)

    df['hour']  = pd.to_datetime(df['timestamp'], unit='ms', errors='coerce').dt.hour.fillna(12)
    df['dow']   = pd.to_datetime(df['timestamp'], unit='ms', errors='coerce').dt.dayofweek.fillna(0)

    # Frequency encodings
    qf = df['question_id'].value_counts(); df['q_freq'] = df['question_id'].map(qf)
    uf = df['user_id'].value_counts();     df['u_freq'] = df['user_id'].map(uf)

    # User-level cumulative stats
    grp = df.groupby('user_id', sort=False)
    df['u_total']   = grp.cumcount()
    df['u_cum_acc'] = grp['correct'].transform(lambda s: s.shift(1).expanding().mean().fillna(0.5))
    df['u_roll5']   = grp['correct'].transform(lambda s: s.shift(1).rolling(5, min_periods=1).mean().fillna(0.5))
    df['u_roll10']  = grp['correct'].transform(lambda s: s.shift(1).rolling(10, min_periods=1).mean().fillna(0.5))
    df['u_roll20']  = grp['correct'].transform(lambda s: s.shift(1).rolling(20, min_periods=1).mean().fillna(0.5))

    # Trend (slope of last 10 answers)
    def _slope(s):
        s = s.shift(1).fillna(0.5)
        out = []
        for i in range(len(s)):
            w = s.iloc[max(0, i-9):i+1].values
            if len(w) < 2:
                out.append(0.0)
            else:
                out.append(float(np.polyfit(range(len(w)), w, 1)[0]))
        return pd.Series(out, index=s.index)
    df['u_trend'] = grp['correct'].transform(_slope)

    df['prev_correct'] = grp['correct'].shift(1).fillna(0.5)

    # Difficulty-level accuracy per user
    diff_acc = df.groupby(['user_id', 'difficulty'])['correct'].transform(
        lambda s: s.shift(1).expanding().mean().fillna(0.5))
    df['u_diff_acc'] = diff_acc

    # Question-level cumulative accuracy
    qgrp = df.groupby('question_id', sort=False)
    df['q_cum_acc'] = qgrp['correct'].transform(lambda s: s.shift(1).expanding().mean().fillna(0.5))
    df['q_hardness'] = 1 - df['q_cum_acc']

    # IRT-like score
    df['ability_delta'] = df['u_cum_acc'] - df['q_cum_acc']
    df['irt_score'] = 1 / (1 + np.exp(-(df['ability_delta'])))

    # Attempt number per (user, question)
    df['attempt_n'] = df.groupby(['user_id', 'question_id']).cumcount()
    df['is_repeat']  = (df['attempt_n'] > 0).astype(int)

    # Time since last attempt of this question
    df['last_q_ts'] = df.groupby('question_id')['timestamp'].shift(1)
    df['log_time_since_q'] = np.log1p(df['timestamp'] - df['last_q_ts'].fillna(df['timestamp']))

    # Session position (gap > 30 min = new session)
    df['ts_diff']    = df.groupby('user_id')['timestamp'].diff().fillna(0)
    df['new_session']= (df['ts_diff'] > 1_800_000).astype(int)
    df['in_sess_pos']= df.groupby(['user_id', df.groupby('user_id')['new_session'].cumsum()]).cumcount()

    # Categorical encodings
    df['user_cat']     = df['user_id'].astype('category').cat.codes
    df['question_cat'] = df['question_id'].astype('category').cat.codes

    feat_cols = [
        'difficulty','hour','dow','q_freq','u_total','u_cum_acc',
        'u_roll5','u_roll10','u_roll20','u_trend','prev_correct',
        'u_diff_acc','q_cum_acc','ability_delta','irt_score',
        'attempt_n','is_repeat','log_time_since_q','in_sess_pos',
        'q_hardness','user_cat','question_cat'
    ]
    X = df[feat_cols].fillna(0)
    y = df['correct']
    return X, y, feat_cols


df_prog = load_csv('progress_training.csv', nrows=80_000)
lgb_prog = joblib.load(os.path.join(MODEL_DIR, 'progress/lgb_model.pkl'))
feat_cols_prog = lgb_prog.feature_name()
print(f'  LGB progress features ({len(feat_cols_prog)}): {feat_cols_prog[:5]}...')

if df_prog is not None and not df_prog.empty:
    print('  Engineering progress features...')
    t0 = time.time()
    X_prog, y_prog, _ = _fe_progress(df_prog)
    print(f'  FE done in {time.time()-t0:.1f}s')

    X_tr, X_te, y_tr, y_te = train_test_split(
        X_prog, y_prog, test_size=0.2, random_state=42, stratify=y_prog)

    # --- 1a. Feature Importance ---
    print('  Plotting feature importance...')
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    fi_split = lgb_prog.feature_importance(importance_type='split')
    fi_gain  = lgb_prog.feature_importance(importance_type='gain')
    fi_df = pd.DataFrame({'feature': feat_cols_prog, 'split': fi_split, 'gain': fi_gain})


    for ax, col, title in zip(axes, ['split', 'gain'], ['Split Frequency', 'Total Gain']):
        top = fi_df.nlargest(20, col)
        sns.barplot(data=top, y='feature', x=col, ax=ax, palette='viridis', orient='h')
        ax.set_title(f'LGB Feature Importance — {title}', fontsize=13, fontweight='bold')
        ax.set_xlabel(title); ax.set_ylabel('')

    savefig('progress/feature_importance.png')

    # --- 1b. ROC Curve + Precision-Recall ---
    print('  Computing ROC + PR curves...')
    y_prob = lgb_prog.predict(X_te)
    auc = roc_auc_score(y_te, y_prob)
    fpr, tpr, _ = roc_curve(y_te, y_prob)
    ap  = average_precision_score(y_te, y_prob)
    prec, rec, _ = precision_recall_curve(y_te, y_prob)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    axes[0].plot(fpr, tpr, color=COLORS[0], lw=2, label=f'LGB AUC = {auc:.4f}')
    axes[0].plot([0,1],[0,1],'k--', lw=1, label='Random')
    axes[0].set(title='ROC Curve — Progress LGB', xlabel='False Positive Rate',
                ylabel='True Positive Rate', xlim=[0,1], ylim=[0,1.02])
    axes[0].legend(loc='lower right', fontsize=11)

    axes[1].plot(rec, prec, color=COLORS[1], lw=2, label=f'AP = {ap:.4f}')
    axes[1].set(title='Precision-Recall Curve — Progress LGB', xlabel='Recall',
                ylabel='Precision', xlim=[0,1], ylim=[0,1.02])
    axes[1].legend(loc='lower left', fontsize=11)

    savefig('progress/roc_pr_curves.png')

    # --- 1c. Confusion Matrix + Threshold Analysis ---
    print('  Plotting confusion matrix + threshold...')
    threshold = 0.5
    try:
        thr_file = os.path.join(MODEL_DIR, 'progress/threshold.pkl')
        if os.path.exists(thr_file):
            threshold = float(joblib.load(thr_file))
    except Exception:
        pass

    y_pred = (y_prob >= threshold).astype(int)
    cm = confusion_matrix(y_te, y_pred)
    thresholds = np.linspace(0.3, 0.8, 50)
    accs   = [accuracy_score(y_te, (y_prob >= t).astype(int)) for t in thresholds]
    f1s    = [f1_score(y_te, (y_prob >= t).astype(int), zero_division=0) for t in thresholds]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=axes[0],
                xticklabels=['Wrong','Correct'], yticklabels=['Wrong','Correct'])
    axes[0].set(title=f'Confusion Matrix (thr={threshold:.2f})',
                xlabel='Predicted', ylabel='Actual')

    axes[1].plot(thresholds, accs, color=COLORS[0], lw=2, label='Accuracy')
    axes[1].plot(thresholds, f1s,  color=COLORS[2], lw=2, label='F1-Score')
    axes[1].axvline(threshold, color='red', ls='--', label=f'Used thr={threshold:.2f}')
    axes[1].set(title='Accuracy & F1 vs Decision Threshold', xlabel='Threshold',
                ylabel='Score', xlim=[0.3, 0.8], ylim=[0.5, 1.0])
    axes[1].legend()

    savefig('progress/confusion_threshold.png')

    # --- 1d. LGB Summary Metrics Bar Chart ---
    print('  LGB summary metrics chart...')
    # RF/XGB progress models were trained on a different (base) feature set and can't be
    # directly compared on the 22-feature test set, so we show LGB metrics per threshold
    thrs_eval = [0.4, 0.45, 0.5, 0.55, 0.6]
    acc_vals = [accuracy_score(y_te, (y_prob >= t).astype(int)) for t in thrs_eval]
    f1_vals  = [f1_score(y_te, (y_prob >= t).astype(int), zero_division=0) for t in thrs_eval]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    x_pos = np.arange(len(thrs_eval))
    axes[0].bar(x_pos, acc_vals, color=COLORS[:len(thrs_eval)], width=0.6)
    for i, v in enumerate(acc_vals):
        axes[0].text(i, v + 0.002, f'{v:.4f}', ha='center', va='bottom', fontsize=10)
    axes[0].set(title='Accuracy at Different Thresholds — Progress LGB',
                xlabel='Decision Threshold', ylabel='Accuracy',
                xticks=x_pos, xticklabels=[f'{t:.2f}' for t in thrs_eval], ylim=[0.5, 1.05])

    axes[1].bar(x_pos, f1_vals, color=COLORS[:len(thrs_eval)], width=0.6)
    for i, v in enumerate(f1_vals):
        axes[1].text(i, v + 0.002, f'{v:.4f}', ha='center', va='bottom', fontsize=10)
    axes[1].set(title='F1-Score at Different Thresholds — Progress LGB',
                xlabel='Decision Threshold', ylabel='F1-Score',
                xticks=x_pos, xticklabels=[f'{t:.2f}' for t in thrs_eval], ylim=[0.5, 1.05])

    savefig('progress/threshold_analysis.png')

    # --- 1e. Calibration Curve ---
    print('  Calibration curve...')
    from sklearn.calibration import calibration_curve
    fraction_pos, mean_pred = calibration_curve(y_te, y_prob, n_bins=15)
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.plot(mean_pred, fraction_pos, 's-', color=COLORS[0], lw=2, label='LGB')
    ax.plot([0,1],[0,1],'k--', lw=1, label='Perfect calibration')
    ax.set(title='Calibration Curve — Progress LGB', xlabel='Mean Predicted Probability',
           ylabel='Fraction of Positives', xlim=[0,1], ylim=[0,1])
    ax.legend()
    savefig('progress/calibration.png')

    save_metrics_row(all_metrics, 'Progress', 'LightGBM',
                     {'AUC': round(auc, 4), 'Avg_Precision': round(ap, 4),
                      'Accuracy': round(accuracy_score(y_te, y_pred), 4),
                      'F1': round(f1_score(y_te, y_pred, zero_division=0), 4)})

print('  Progress plots done.\n')


# ─────────────────────────────────────────────────────────────
# 2. MOTIVATION AGENT — Retrain + Evaluate
# ─────────────────────────────────────────────────────────────
print('[2/4] MOTIVATION AGENT ─────────────────────────────────')

df_mot = load_csv('motivation_training.csv', nrows=5_000)

if df_mot is not None and not df_mot.empty:
    # Identify target: 'stress_level' (0/1/2 integer from first dataset)
    # and remove leaky columns
    LEAK_COLS = {'stress_level', 'Stress_Score', 'Stress_Level'}
    target_col = 'stress_level'

    num_cols = df_mot.select_dtypes(include='number').columns.tolist()
    feat_cols_mot = [c for c in num_cols
                     if c not in LEAK_COLS and 'unnamed' not in c.lower()]
    # Sanitize feature names: LightGBM rejects special JSON characters
    import re as _re
    def _sanitize(name):
        return _re.sub(r'[^A-Za-z0-9_]', '_', name)
    feat_cols_mot_safe = [_sanitize(c) for c in feat_cols_mot]
    # Deduplicate sanitized names
    seen = {}
    feat_cols_mot_safe_unique = []
    for s in feat_cols_mot_safe:
        if s in seen:
            seen[s] += 1
            feat_cols_mot_safe_unique.append(f'{s}_{seen[s]}')
        else:
            seen[s] = 0
            feat_cols_mot_safe_unique.append(s)
    feat_cols_mot_safe = feat_cols_mot_safe_unique
    print(f'  Motivation features: {len(feat_cols_mot)} — {feat_cols_mot[:5]}...')

    y_mot_raw = df_mot[target_col].dropna()
    df_mot_clean = df_mot.loc[y_mot_raw.index, feat_cols_mot].fillna(0)
    y_mot = y_mot_raw.astype(int)

    # Label-encode to 0/1/2 in case not already
    le_mot = LabelEncoder()
    y_mot = pd.Series(le_mot.fit_transform(y_mot), index=df_mot_clean.index)
    n_classes = len(le_mot.classes_)
    print(f'  Classes: {le_mot.classes_}  n={n_classes}')

    X_tr_m, X_te_m, y_tr_m, y_te_m = train_test_split(
        df_mot_clean, y_mot, test_size=0.2, random_state=42, stratify=y_mot)

    scaler_mot = StandardScaler()
    X_tr_ms = scaler_mot.fit_transform(X_tr_m)
    X_te_ms  = scaler_mot.transform(X_te_m)

    # Train RF
    print('  Training RF...')
    rf_mot = RandomForestClassifier(n_estimators=200, max_depth=15,
                                    min_samples_leaf=10, random_state=42, n_jobs=-1)
    rf_mot.fit(X_tr_ms, y_tr_m)

    # Train XGB
    print('  Training XGB...')
    xgb_mot = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.05,
                             n_jobs=-1, random_state=42, eval_metric='mlogloss',
                             use_label_encoder=False)
    xgb_mot.fit(X_tr_ms, y_tr_m, eval_set=[(X_te_ms, y_te_m)], verbose=False)

    # Train LGB (with proper feature names — sanitized for JSON safety)
    print('  Training LGB...')
    dtrain = lgb.Dataset(X_tr_m.values, label=y_tr_m.values,
                         feature_name=feat_cols_mot_safe)
    dval   = lgb.Dataset(X_te_m.values, label=y_te_m.values,
                         feature_name=feat_cols_mot_safe, reference=dtrain)
    params = dict(objective='multiclass', num_class=n_classes, metric='multi_logloss',
                  learning_rate=0.05, num_leaves=63, min_child_samples=20,
                  subsample=0.8, colsample_bytree=0.8, verbose=-1, seed=42)
    lgb_mot = lgb.train(params, dtrain, num_boost_round=300,
                        valid_sets=[dval],
                        callbacks=[lgb.early_stopping(30, verbose=False),
                                   lgb.log_evaluation(period=-1)])
    print(f'  LGB best iteration: {lgb_mot.best_iteration}')

    # Save fixed models
    print('  Saving re-trained models...')
    os.makedirs(os.path.join(MODEL_DIR, 'motivation'), exist_ok=True)
    joblib.dump(scaler_mot, os.path.join(MODEL_DIR, 'motivation/scaler.pkl'))
    joblib.dump(rf_mot,     os.path.join(MODEL_DIR, 'motivation/rf.pkl'))
    joblib.dump(xgb_mot,    os.path.join(MODEL_DIR, 'motivation/xgb.pkl'))
    lgb_mot.save_model(os.path.join(MODEL_DIR, 'motivation/lgb_model.pkl'))
    joblib.dump(feat_cols_mot,      os.path.join(MODEL_DIR, 'motivation/feat_cols.pkl'))
    joblib.dump(feat_cols_mot_safe, os.path.join(MODEL_DIR, 'motivation/feat_cols_safe.pkl'))
    joblib.dump(le_mot,             os.path.join(MODEL_DIR, 'motivation/label_encoder.pkl'))
    print('  Motivation models saved.')

    # Evaluate
    rf_prob  = rf_mot.predict_proba(X_te_ms)
    xgb_prob = xgb_mot.predict_proba(X_te_ms)
    lgb_prob = lgb_mot.predict(X_te_m.values)

    rf_pred_m  = rf_mot.predict(X_te_ms)
    xgb_pred_m = xgb_mot.predict(X_te_ms)
    lgb_pred_m = np.argmax(lgb_prob, axis=1)

    def _multiclass_metrics(y_true, y_pred, y_prob, name):
        acc = accuracy_score(y_true, y_pred)
        f1  = f1_score(y_true, y_pred, average='weighted', zero_division=0)
        try:
            auc_ov = roc_auc_score(y_true, y_prob, multi_class='ovr', average='weighted')
        except Exception:
            auc_ov = float('nan')
        ll = log_loss(y_true, y_prob)
        print(f'  {name}: acc={acc:.4f}  f1={f1:.4f}  auc={auc_ov:.4f}  logloss={ll:.4f}')
        return {'Accuracy': round(acc,4), 'F1_weighted': round(f1,4),
                'AUC_OvR': round(auc_ov,4), 'LogLoss': round(ll,4)}

    mets_rf  = _multiclass_metrics(y_te_m, rf_pred_m,  rf_prob,  'RF')
    mets_xgb = _multiclass_metrics(y_te_m, xgb_pred_m, xgb_prob, 'XGB')
    mets_lgb = _multiclass_metrics(y_te_m, lgb_pred_m, lgb_prob, 'LGB')

    save_metrics_row(all_metrics, 'Motivation', 'RandomForest',  mets_rf)
    save_metrics_row(all_metrics, 'Motivation', 'XGBoost',       mets_xgb)
    save_metrics_row(all_metrics, 'Motivation', 'LightGBM',      mets_lgb)

    class_names = [str(c) for c in le_mot.classes_]
    label_map   = {0: 'Low', 1: 'Medium', 2: 'High'} if n_classes == 3 else {}
    display_labels = [label_map.get(int(c), str(c)) for c in le_mot.classes_]

    # --- 2a. Confusion Matrices ---
    print('  Plotting confusion matrices...')
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    for ax, pred, title in zip(axes,
                                [rf_pred_m, xgb_pred_m, lgb_pred_m],
                                ['Random Forest', 'XGBoost', 'LightGBM']):
        cm = confusion_matrix(y_te_m, pred)
        cm_norm = cm.astype('float') / cm.sum(axis=1, keepdims=True)
        sns.heatmap(cm_norm, annot=True, fmt='.2f', cmap='Blues', ax=ax,
                    xticklabels=display_labels, yticklabels=display_labels,
                    vmin=0, vmax=1)
        acc_v = accuracy_score(y_te_m, pred)
        ax.set(title=f'{title}\n(Acc={acc_v:.3f})',
               xlabel='Predicted', ylabel='Actual')

    fig.suptitle('Normalised Confusion Matrices — Motivation Agent', fontsize=14, fontweight='bold', y=1.02)
    savefig('motivation/confusion_matrices.png')

    # --- 2b. Model Comparison Bar Charts ---
    print('  Plotting model comparison...')
    metrics_labels = ['Accuracy', 'F1_weighted', 'AUC_OvR', 'LogLoss']
    models_data = {
        'RandomForest': mets_rf,
        'XGBoost':      mets_xgb,
        'LightGBM':     mets_lgb,
    }
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    for ax, metric in zip(axes.flat, metrics_labels):
        vals = [models_data[m][metric] for m in models_data]
        bars = ax.bar(list(models_data.keys()), vals, color=COLORS[:3], width=0.5)
        for b in bars:
            ax.text(b.get_x()+b.get_width()/2, b.get_height()+0.002,
                    f'{b.get_height():.4f}', ha='center', va='bottom', fontsize=10)
        ax.set(title=f'{metric}', ylabel=metric)
        if metric == 'LogLoss':
            ax.invert_yaxis()
    fig.suptitle('Model Comparison — Motivation Agent', fontsize=14, fontweight='bold')
    savefig('motivation/model_comparison.png')

    # --- 2c. Feature Importance ---
    print('  Plotting feature importances...')
    rf_fi  = pd.Series(rf_mot.feature_importances_, index=feat_cols_mot).nlargest(20)
    lgb_fi = pd.Series(lgb_mot.feature_importance(importance_type='gain'),
                       index=feat_cols_mot_safe).nlargest(20)

    fig, axes = plt.subplots(1, 2, figsize=(18, 8))
    rf_fi.sort_values().plot.barh(ax=axes[0], color=COLORS[0])
    axes[0].set(title='RF Feature Importance (Gini)', xlabel='Importance')

    lgb_fi.sort_values().plot.barh(ax=axes[1], color=COLORS[2])
    axes[1].set(title='LGB Feature Importance (Gain)', xlabel='Importance')

    fig.suptitle('Top-20 Feature Importances — Motivation Agent', fontsize=14, fontweight='bold')
    savefig('motivation/feature_importance.png')

    # --- 2d. Per-class F1 comparison ---
    print('  Per-class F1 bar chart...')
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(n_classes)
    w = 0.25
    for i, (name, pred) in enumerate([('RF', rf_pred_m), ('XGB', xgb_pred_m), ('LGB', lgb_pred_m)]):
        report  = classification_report(y_te_m, pred, output_dict=True, zero_division=0)
        f1_vals = [report[str(c)]['f1-score'] for c in range(n_classes)]
        bars = ax.bar(x + i*w, f1_vals, w, label=name, color=COLORS[i])
        for b in bars:
            ax.text(b.get_x()+b.get_width()/2, b.get_height()+0.005,
                    f'{b.get_height():.2f}', ha='center', va='bottom', fontsize=9)
    ax.set(title='Per-Class F1-Score — Motivation Agent', xlabel='Stress Level',
           ylabel='F1-Score', xticks=x+w, xticklabels=display_labels, ylim=[0, 1.1])
    ax.legend()
    savefig('motivation/per_class_f1.png')

    # --- 2e. Learning Curves ---
    print('  Learning curves...')
    from sklearn.model_selection import learning_curve
    train_sizes, tr_scores, cv_scores = learning_curve(
        RandomForestClassifier(n_estimators=50, max_depth=8, random_state=42, n_jobs=-1),
        X_tr_ms, y_tr_m, cv=3, train_sizes=np.linspace(0.1, 1.0, 6),
        scoring='f1_weighted', n_jobs=-1)
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.fill_between(train_sizes, tr_scores.mean(1)-tr_scores.std(1),
                    tr_scores.mean(1)+tr_scores.std(1), alpha=0.15, color=COLORS[0])
    ax.fill_between(train_sizes, cv_scores.mean(1)-cv_scores.std(1),
                    cv_scores.mean(1)+cv_scores.std(1), alpha=0.15, color=COLORS[1])
    ax.plot(train_sizes, tr_scores.mean(1), 'o-', color=COLORS[0], label='Train F1')
    ax.plot(train_sizes, cv_scores.mean(1), 's-', color=COLORS[1], label='CV F1')
    ax.set(title='Learning Curve — Motivation RF', xlabel='Training Samples', ylabel='F1-Score')
    ax.legend()
    savefig('motivation/learning_curve.png')

print('  Motivation plots done.\n')


# ─────────────────────────────────────────────────────────────
# 3. PROFILING AGENT — Retrain KMeans + Evaluate
# ─────────────────────────────────────────────────────────────
print('[3/4] PROFILING AGENT ─────────────────────────────────')

df_prof = load_csv('profiling_training.csv', nrows=30_000)

if df_prof is not None and not df_prof.empty:
    # Select meaningful numeric features — exclude ID and grade columns
    EXCLUDE_PROF = {'user_id', 'grade', 'final_grade'}
    num_cols_p = df_prof.select_dtypes(include='number').columns.tolist()
    feat_cols_prof = [c for c in num_cols_p
                      if c not in EXCLUDE_PROF and 'unnamed' not in c.lower()]
    print(f'  Profiling features ({len(feat_cols_prof)}): {feat_cols_prof}')

    X_prof = df_prof[feat_cols_prof].dropna()
    print(f'  Samples after dropna: {len(X_prof):,}')

    scaler_prof = StandardScaler()
    X_prof_sc   = scaler_prof.fit_transform(X_prof)

    # --- 3a. Elbow Curve + Silhouette ---
    print('  Elbow + silhouette analysis...')
    k_range    = range(2, 8)  # k=2..7 for speed
    inertias   = []
    sil_scores = []
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=5, max_iter=100)
        labels = km.fit_predict(X_prof_sc)
        inertias.append(km.inertia_)
        # Use sample for silhouette — O(n²) is infeasible for large n
        sil_sample = min(5000, len(X_prof_sc))
        sil_scores.append(silhouette_score(X_prof_sc, labels, sample_size=sil_sample, random_state=42))
        print(f'    k={k}: inertia={km.inertia_:.0f}  silhouette={sil_scores[-1]:.4f}')

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    axes[0].plot(list(k_range), inertias, 'o-', color=COLORS[0], lw=2)
    axes[0].set(title='Elbow Curve — KMeans Inertia vs k',
                xlabel='Number of Clusters (k)', ylabel='Inertia (SSE)')

    axes[1].plot(list(k_range), sil_scores, 's-', color=COLORS[2], lw=2)
    best_k = list(k_range)[np.argmax(sil_scores)]
    axes[1].axvline(best_k, color='red', ls='--', label=f'Best k={best_k}')
    axes[1].set(title='Silhouette Score vs k',
                xlabel='Number of Clusters (k)', ylabel='Silhouette Score')
    axes[1].legend()

    savefig('profiling/elbow_silhouette.png')

    # Train final model with best k (from silhouette) or k=4
    best_k = max(3, best_k)  # at least 3 clusters
    print(f'  Training final KMeans with k={best_k}...')
    kmeans_prof = KMeans(n_clusters=best_k, random_state=42, n_init=5, max_iter=200)
    labels_prof = kmeans_prof.fit_predict(X_prof_sc)

    gmm_prof = GaussianMixture(n_components=best_k, random_state=42)
    gmm_prof.fit(X_prof_sc)
    labels_gmm = gmm_prof.predict(X_prof_sc)

    # Save fixed models
    print('  Saving re-trained profiling models...')
    os.makedirs(os.path.join(MODEL_DIR, 'profiling'), exist_ok=True)
    joblib.dump(scaler_prof,  os.path.join(MODEL_DIR, 'profiling/scaler.pkl'))
    joblib.dump(kmeans_prof,  os.path.join(MODEL_DIR, 'profiling/kmeans.pkl'))
    joblib.dump(gmm_prof,     os.path.join(MODEL_DIR, 'profiling/gmm.pkl'))
    joblib.dump(feat_cols_prof, os.path.join(MODEL_DIR, 'profiling/feat_cols.pkl'))
    print('  Profiling models saved.')

    sil_final = silhouette_score(X_prof_sc, labels_prof, sample_size=5000, random_state=42)
    print(f'  Final KMeans silhouette={sil_final:.4f}')
    save_metrics_row(all_metrics, 'Profiling', f'KMeans (k={best_k})',
                     {'Silhouette': round(sil_final, 4),
                      'Inertia': round(kmeans_prof.inertia_, 2)})

    # --- 3b. PCA Scatter ---
    print('  PCA scatter plot...')
    pca   = PCA(n_components=2, random_state=42)
    X_pca = pca.fit_transform(X_prof_sc)
    evr   = pca.explained_variance_ratio_

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    for ax, lbls, title in zip(axes,
                                [labels_prof, labels_gmm],
                                [f'KMeans (k={best_k})', f'GMM (k={best_k})']):
        for c in range(best_k):
            mask = (lbls == c)
            ax.scatter(X_pca[mask, 0], X_pca[mask, 1],
                       s=10, alpha=0.4, color=COLORS[c], label=f'Cluster {c}')
        ax.set(title=f'{title} — PCA Projection\nPC1={evr[0]*100:.1f}%  PC2={evr[1]*100:.1f}%',
               xlabel='PC1', ylabel='PC2')
        ax.legend(markerscale=3)
    fig.suptitle('Learner Cluster Projections — Profiling Agent', fontsize=14, fontweight='bold')
    savefig('profiling/pca_scatter.png')

    # --- 3c. Cluster Profiles (mean feature values) ---
    print('  Cluster profile heatmap...')
    X_prof_df        = pd.DataFrame(X_prof.values, columns=feat_cols_prof)
    X_prof_df['cluster'] = labels_prof
    cluster_means = X_prof_df.groupby('cluster')[feat_cols_prof].mean()
    # Normalized to [0,1] per feature for readability
    cluster_norm  = (cluster_means - cluster_means.min()) / \
                    (cluster_means.max() - cluster_means.min() + 1e-9)

    fig, ax = plt.subplots(figsize=(14, max(5, best_k * 1.5)))
    sns.heatmap(cluster_norm, annot=True, fmt='.2f', cmap='YlOrRd', ax=ax,
                linewidths=0.5)
    ax.set(title=f'Cluster Profile Heatmap (Normalised) — k={best_k}',
           xlabel='Feature', ylabel='Cluster')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=40, ha='right')
    savefig('profiling/cluster_profiles.png')

    # --- 3d. Feature Contribution to Clusters (variance) ---
    print('  Feature variance across clusters...')
    cluster_std = X_prof_df.groupby('cluster')[feat_cols_prof].std().mean()
    cluster_std_sorted = cluster_std.sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(12, 6))
    cluster_std_sorted.plot.bar(ax=ax, color=COLORS[0])
    ax.set(title='Feature Variability Across Clusters (Mean Std Dev)',
           xlabel='Feature', ylabel='Mean Std Dev')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=40, ha='right')
    savefig('profiling/feature_variance.png')

print('  Profiling plots done.\n')


# ─────────────────────────────────────────────────────────────
# 4. RESCHEDULE AGENT — Stacking + Evaluate
# ─────────────────────────────────────────────────────────────
print('[4/4] RESCHEDULE AGENT ─────────────────────────────────')

def _fe_reschedule(df):
    """Replicate the 9-feature engineering for reschedule models."""
    df = df.copy()
    df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
    df['next_ts']   = pd.to_numeric(df['next_ts'],   errors='coerce')
    df['delta_s']   = pd.to_numeric(df['delta_s'],   errors='coerce')
    df = df.sort_values(['user_id', 'timestamp']).dropna(subset=['delta_s'])

    df['q_freq']  = df['question_id'].map(df['question_id'].value_counts())
    df['u_freq']  = df['user_id'].map(df['user_id'].value_counts())
    df['hour']    = pd.to_datetime(df['timestamp'], unit='ms', errors='coerce').dt.hour.fillna(12)
    df['dow']     = pd.to_datetime(df['timestamp'], unit='ms', errors='coerce').dt.dayofweek.fillna(0)

    grp = df.groupby('user_id')
    df['u_count']      = grp.cumcount()
    df['u_mean_delta'] = grp['delta_s'].transform(lambda s: s.shift(1).expanding().mean().fillna(s.median()))
    df['u_std_delta']  = grp['delta_s'].transform(lambda s: s.shift(1).expanding().std().fillna(1.0))
    df['is_long_gap']  = (df['delta_s'] > df['delta_s'].quantile(0.75)).astype(int)

    feat_cols = ['correct','q_freq','u_freq','hour','dow',
                 'u_count','u_mean_delta','u_std_delta','is_long_gap']
    X = df[feat_cols].fillna(0)
    y = np.log1p(df['delta_s'].clip(lower=0))  # log1p target for stability
    return X, y, feat_cols


df_resched = load_csv('reschedule_training.csv', nrows=80_000)

if df_resched is not None and not df_resched.empty:
    print('  Engineering reschedule features...')
    X_rs, y_rs, feat_cols_rs = _fe_reschedule(df_resched)
    X_tr_rs, X_te_rs, y_tr_rs, y_te_rs = train_test_split(
        X_rs, y_rs, test_size=0.2, random_state=42)

    scaler_rs = joblib.load(os.path.join(MODEL_DIR, 'reschedule/scaler_fe.pkl'))
    X_tr_rss  = scaler_rs.transform(X_tr_rs)
    X_te_rss  = scaler_rs.transform(X_te_rs)

    # Load all reschedule models
    lgb_rs   = joblib.load(os.path.join(MODEL_DIR, 'reschedule/lgb_fe_model.pkl'))
    rf_rs    = joblib.load(os.path.join(MODEL_DIR, 'reschedule/rf_fe_best.pkl'))
    xgb_rs   = joblib.load(os.path.join(MODEL_DIR, 'reschedule/xgb_best.pkl'))
    stack_rs = joblib.load(os.path.join(MODEL_DIR, 'reschedule/stack_fe_model.pkl'))

    def _rs_predict(model, X, X_sc):
        """Handle both Booster and sklearn interfaces."""
        if isinstance(model, lgb.Booster):
            return model.predict(X.values)
        else:
            return model.predict(X_sc)

    preds = {
        'LightGBM':    _rs_predict(lgb_rs,   X_te_rs, X_te_rss),
        'RandomForest': _rs_predict(rf_rs,   X_te_rs, X_te_rss),
        'XGBoost':     _rs_predict(xgb_rs,   X_te_rs, X_te_rss),
        'Stacking':    _rs_predict(stack_rs, X_te_rs, X_te_rss),
    }

    def _regression_metrics(y_true, y_pred, name):
        mae  = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        r2   = 1 - np.sum((y_true - y_pred)**2) / np.sum((y_true - y_true.mean())**2)
        print(f'  {name}: MAE={mae:.4f}  RMSE={rmse:.4f}  R2={r2:.4f}')
        return {'MAE': round(mae,4), 'RMSE': round(rmse,4), 'R2': round(r2,4)}

    for mname, pred in preds.items():
        mets = _regression_metrics(y_te_rs, pred, mname)
        save_metrics_row(all_metrics, 'Reschedule', mname, mets)

    # --- 4a. MAE / RMSE Comparison ---
    print('  Plotting MAE/RMSE comparison...')
    mae_vals  = [mean_absolute_error(y_te_rs, preds[m]) for m in preds]
    rmse_vals = [np.sqrt(mean_squared_error(y_te_rs, preds[m])) for m in preds]
    r2_vals   = [1 - np.sum((y_te_rs - preds[m])**2) /
                 np.sum((y_te_rs - y_te_rs.mean())**2) for m in preds]
    mnames = list(preds.keys())

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    for ax, vals, title, col in zip(axes,
                                     [mae_vals, rmse_vals, r2_vals],
                                     ['MAE (log scale)', 'RMSE (log scale)', 'R²'],
                                     COLORS[:3]):
        bars = ax.bar(mnames, vals, color=COLORS[:4], width=0.5)
        for b in bars:
            ax.text(b.get_x()+b.get_width()/2, b.get_height()+0.002,
                    f'{b.get_height():.4f}', ha='center', va='bottom', fontsize=10)
        ax.set(title=title, ylabel=title)
        ax.set_xticklabels(mnames, rotation=20, ha='right')
    fig.suptitle('Model Comparison — Reschedule Agent', fontsize=14, fontweight='bold')
    savefig('reschedule/model_comparison.png')

    # --- 4b. Predicted vs Actual (scatter) ---
    print('  Predicted vs actual scatter...')
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    for ax, (mname, pred) in zip(axes.flat, preds.items()):
        # Sample for scatter clarity
        idx = np.random.choice(len(y_te_rs), min(3000, len(y_te_rs)), replace=False)
        ax.scatter(y_te_rs.iloc[idx], pred[idx], alpha=0.3, s=8, color=COLORS[0])
        lim = [min(y_te_rs.min(), pred.min()), max(y_te_rs.max(), pred.max())]
        ax.plot(lim, lim, 'r--', lw=1.5, label='y=x')
        mae_v  = mean_absolute_error(y_te_rs, pred)
        r2_v   = 1 - np.sum((y_te_rs - pred)**2)/np.sum((y_te_rs - y_te_rs.mean())**2)
        ax.set(title=f'{mname}\nMAE={mae_v:.4f}  R²={r2_v:.4f}',
               xlabel='Actual (log1p seconds)', ylabel='Predicted (log1p seconds)')
        ax.legend()
    fig.suptitle('Predicted vs Actual — Reschedule Agent', fontsize=14, fontweight='bold')
    savefig('reschedule/predicted_vs_actual.png')

    # --- 4c. Residuals ---
    print('  Residuals histograms...')
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    for ax, (mname, pred) in zip(axes.flat, preds.items()):
        residuals = y_te_rs.values - pred
        ax.hist(residuals, bins=60, color=COLORS[0], edgecolor='white', alpha=0.8)
        ax.axvline(0, color='red', ls='--', lw=1.5)
        ax.axvline(residuals.mean(), color='orange', ls='--', lw=1.5,
                   label=f'mean={residuals.mean():.3f}')
        ax.set(title=f'{mname} Residuals', xlabel='Residual (log1p sec)', ylabel='Count')
        ax.legend()
    fig.suptitle('Residual Distributions — Reschedule Agent', fontsize=14, fontweight='bold')
    savefig('reschedule/residuals.png')

    # --- 4d. Feature Importance ---
    print('  Feature importances...')
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    for ax, (mname, model) in zip(axes.flat, [
        ('LightGBM', lgb_rs), ('RandomForest', rf_rs),
        ('XGBoost', xgb_rs), ('Stacking', stack_rs)
    ]):
        try:
            if isinstance(model, lgb.Booster):
                fi = pd.Series(model.feature_importance(importance_type='gain'),
                               index=model.feature_name())
            elif hasattr(model, 'feature_importances_'):
                fi = pd.Series(model.feature_importances_, index=feat_cols_rs)
            elif hasattr(model, 'estimators_'):  # stacking
                fi = pd.Series(
                    np.mean([e.feature_importances_ for e in model.estimators_], axis=0),
                    index=feat_cols_rs)
            else:
                ax.text(0.5, 0.5, 'N/A', ha='center', va='center', transform=ax.transAxes)
                continue
            fi.sort_values().plot.barh(ax=ax, color=COLORS[1])
            ax.set(title=f'{mname} Feature Importance', xlabel='Importance')
        except Exception as e:
            ax.text(0.5, 0.5, str(e)[:60], ha='center', va='center',
                    transform=ax.transAxes, wrap=True)

    fig.suptitle('Feature Importances — Reschedule Agent', fontsize=14, fontweight='bold')
    savefig('reschedule/feature_importance.png')

    # --- 4e. Error vs Actual Value ---
    print('  Error distribution plot...')
    fig, ax = plt.subplots(figsize=(12, 6))
    for i, (mname, pred) in enumerate(preds.items()):
        abs_err = np.abs(y_te_rs.values - pred)
        ax.plot(sorted(y_te_rs.values), sorted(abs_err), lw=1.5,
                label=mname, color=COLORS[i], alpha=0.8)
    ax.set(title='Absolute Error Distribution — Reschedule Agent',
           xlabel='Actual (sorted)', ylabel='Absolute Error (log1p sec)')
    ax.legend()
    savefig('reschedule/error_distribution.png')

print('  Reschedule plots done.\n')


# ─────────────────────────────────────────────────────────────
# 5. SUMMARY TABLE + OVERVIEW
# ─────────────────────────────────────────────────────────────
print('[5/5] SUMMARY METRICS ─────────────────────────────────')

summary_df = pd.DataFrame(all_metrics)
summary_path = os.path.join(OUT_DIR, 'summary/metrics_table.csv')
summary_df.to_csv(summary_path, index=False)
print(f'  Metrics table → {summary_path}')
print()
print(summary_df.to_string(index=False))

# Visual summary table
fig, ax = plt.subplots(figsize=(16, max(4, len(summary_df) * 0.6 + 2)))
ax.axis('off')
col_labels = list(summary_df.columns)
cell_text  = summary_df.fillna('–').values.tolist()
table = ax.table(cellText=cell_text, colLabels=col_labels,
                 cellLoc='center', loc='center',
                 colColours=[COLORS[0]] * len(col_labels))
table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1.1, 1.8)
for (r, c), cell in table.get_celld().items():
    if r == 0:
        cell.set_text_props(fontweight='bold', color='white')
    cell.set_edgecolor('white')
    if r > 0 and r % 2 == 0:
        cell.set_facecolor('#f0f4ff')
ax.set_title('AI-Powered Learning System — ML Evaluation Summary',
             fontsize=14, fontweight='bold', pad=20)
savefig('summary/metrics_overview.png', tight=False)

# ─────────────────────────────────────────────────────────────
# 6. VARIANCE-ACCURACY ANALYSIS (per dataset size)
# ─────────────────────────────────────────────────────────────
print('\n[6/6] VARIANCE-ACCURACY ANALYSIS ──────────────────────')
if df_mot is not None and not df_mot.empty:
    print('  Variance-accuracy on motivation dataset...')
    sizes = [0.1, 0.25, 0.5, 0.75, 1.0]
    results = {'RF': [], 'XGB': [], 'LGB': []}

    for frac in sizes:
        n = max(200, int(len(X_tr_m) * frac))
        idx = np.random.RandomState(42).choice(len(X_tr_m), n, replace=False)
        X_sub = X_tr_ms[idx]; y_sub = y_tr_m.iloc[idx]

        # RF
        rf_tmp = RandomForestClassifier(n_estimators=100, max_depth=10,
                                        random_state=42, n_jobs=-1).fit(X_sub, y_sub)
        results['RF'].append(accuracy_score(y_te_m, rf_tmp.predict(X_te_ms)))

        # XGB
        xgb_tmp = XGBClassifier(n_estimators=100, max_depth=5,
                                 random_state=42, n_jobs=-1,
                                 eval_metric='mlogloss', use_label_encoder=False
                                 ).fit(X_sub, y_sub, verbose=False)
        results['XGB'].append(accuracy_score(y_te_m, xgb_tmp.predict(X_te_ms)))

        # LGB
        ds_tmp = lgb.Dataset(X_sub, label=y_sub, feature_name=feat_cols_mot)
        lgb_tmp = lgb.train({'objective':'multiclass','num_class':n_classes,
                              'verbose':-1,'seed':42,'num_leaves':31},
                            ds_tmp, num_boost_round=100)
        pred_tmp = np.argmax(lgb_tmp.predict(X_te_m.values), axis=1)
        results['LGB'].append(accuracy_score(y_te_m, pred_tmp))

        print(f'  frac={frac:.0%} ({n:,} samples) RF={results["RF"][-1]:.4f} '
              f'XGB={results["XGB"][-1]:.4f} LGB={results["LGB"][-1]:.4f}')

    sample_counts = [max(200, int(len(X_tr_m)*f)) for f in sizes]

    fig, ax = plt.subplots(figsize=(12, 7))
    for mname, accs in results.items():
        ax.plot(sample_counts, accs, 'o-', lw=2, label=mname)
    ax.set(title='Accuracy vs Training Set Size — Motivation Agent',
           xlabel='Training Samples', ylabel='Test Accuracy')
    ax.legend()
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{int(x):,}'))
    savefig('summary/variance_accuracy.png')

print('\n' + '='*60)
print(f' All plots saved to {OUT_DIR}')
print('='*60 + '\n')
