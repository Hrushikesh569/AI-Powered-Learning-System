"""
evaluate_remaining.py — Profiling + Reschedule + Summary plots only.
Run after evaluate_all.py has completed progress + motivation sections.

docker exec docker-backend-1 python /app/evaluate_remaining.py
"""
import os, warnings
import numpy as np
import pandas as pd
import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture
from sklearn.decomposition import PCA
from sklearn.metrics import (
    silhouette_score, mean_absolute_error, mean_squared_error
)
import lightgbm as lgb

warnings.filterwarnings('ignore')

TRAINING_DIR = '/app/training_data'
MODEL_DIR    = '/app/app/ml'
OUT_DIR      = '/app/evaluation_plots'
DPI          = 150

os.makedirs(OUT_DIR, exist_ok=True)
for sub in ('profiling', 'reschedule', 'summary'):
    os.makedirs(os.path.join(OUT_DIR, sub), exist_ok=True)

sns.set_theme(style='whitegrid', palette='muted', font_scale=1.1)
COLORS = sns.color_palette('muted', 8)


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
        print(f'  [WARN] {name} not found')
        return None
    if nrows is None:
        size_mb = os.path.getsize(path) / 1e6
        if size_mb > 150:
            nrows = 200_000
    df = pd.read_csv(path, nrows=nrows)
    print(f'  Loaded {name}: {df.shape[0]:,} rows × {df.shape[1]} cols')
    return df


all_metrics = []

def save_metrics_row(store, agent, model, metrics_dict):
    store.append({'agent': agent, 'model': model, **metrics_dict})


# ─────────────────────────────────────────────────────────────
# 3. PROFILING AGENT — Retrain KMeans + Evaluate
# ─────────────────────────────────────────────────────────────
print('\n[1/3] PROFILING AGENT ─────────────────────────────────')

df_prof = load_csv('profiling_training.csv', nrows=30_000)

if df_prof is not None and not df_prof.empty:
    EXCLUDE_PROF = {'user_id', 'grade', 'final_grade'}
    num_cols_p = df_prof.select_dtypes(include='number').columns.tolist()
    feat_cols_prof = [c for c in num_cols_p
                      if c not in EXCLUDE_PROF and 'unnamed' not in c.lower()]
    print(f'  Profiling features ({len(feat_cols_prof)}): {feat_cols_prof}')

    X_prof = df_prof[feat_cols_prof].dropna()
    print(f'  Samples after dropna: {len(X_prof):,}')

    scaler_prof = StandardScaler()
    X_prof_sc   = scaler_prof.fit_transform(X_prof)

    # --- Elbow + Silhouette (fast, sampled) ---
    print('  Elbow + silhouette analysis...')
    k_range    = range(2, 8)
    inertias   = []
    sil_scores = []
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=5, max_iter=100)
        labels = km.fit_predict(X_prof_sc)
        inertias.append(km.inertia_)
        sil_sample = min(3000, len(X_prof_sc))
        sil_scores.append(silhouette_score(X_prof_sc, labels,
                                           sample_size=sil_sample, random_state=42))
        print(f'    k={k}: inertia={km.inertia_:.0f}  silhouette={sil_scores[-1]:.4f}')

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    axes[0].plot(list(k_range), inertias, 'o-', color=COLORS[0], lw=2)
    axes[0].set(title='Elbow Curve — KMeans Inertia vs k',
                xlabel='Number of Clusters (k)', ylabel='Inertia (SSE)')

    best_k = list(k_range)[np.argmax(sil_scores)]
    axes[1].plot(list(k_range), sil_scores, 's-', color=COLORS[2], lw=2)
    axes[1].axvline(best_k, color='red', ls='--', label=f'Best k={best_k}')
    axes[1].set(title='Silhouette Score vs k',
                xlabel='Number of Clusters (k)', ylabel='Silhouette Score')
    axes[1].legend()
    savefig('profiling/elbow_silhouette.png')

    best_k = max(3, best_k)
    print(f'  Training final KMeans k={best_k}...')
    kmeans_prof = KMeans(n_clusters=best_k, random_state=42, n_init=5, max_iter=300)
    labels_prof = kmeans_prof.fit_predict(X_prof_sc)

    gmm_prof = GaussianMixture(n_components=best_k, random_state=42)
    gmm_prof.fit(X_prof_sc)
    labels_gmm = gmm_prof.predict(X_prof_sc)

    # Save
    os.makedirs(os.path.join(MODEL_DIR, 'profiling'), exist_ok=True)
    joblib.dump(scaler_prof,     os.path.join(MODEL_DIR, 'profiling/scaler.pkl'))
    joblib.dump(kmeans_prof,     os.path.join(MODEL_DIR, 'profiling/kmeans.pkl'))
    joblib.dump(gmm_prof,        os.path.join(MODEL_DIR, 'profiling/gmm.pkl'))
    joblib.dump(feat_cols_prof,  os.path.join(MODEL_DIR, 'profiling/feat_cols.pkl'))
    print('  Profiling models saved.')

    sil_final = silhouette_score(X_prof_sc, labels_prof, sample_size=3000, random_state=42)
    print(f'  Final KMeans silhouette={sil_final:.4f}')
    save_metrics_row(all_metrics, 'Profiling', f'KMeans (k={best_k})',
                     {'Silhouette': round(sil_final, 4),
                      'Inertia': round(kmeans_prof.inertia_, 2)})

    # --- PCA Scatter ---
    print('  PCA scatter...')
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
                       s=8, alpha=0.3, color=COLORS[c], label=f'Cluster {c}')
        ax.set(title=f'{title}\nPC1={evr[0]*100:.1f}%  PC2={evr[1]*100:.1f}%',
               xlabel='PC1', ylabel='PC2')
        ax.legend(markerscale=3)
    fig.suptitle('Learner Cluster Projections — Profiling Agent',
                 fontsize=14, fontweight='bold')
    savefig('profiling/pca_scatter.png')

    # --- Cluster Profiles ---
    print('  Cluster profile heatmap...')
    X_prof_df        = pd.DataFrame(X_prof.values, columns=feat_cols_prof)
    X_prof_df['cluster'] = labels_prof
    cluster_means = X_prof_df.groupby('cluster')[feat_cols_prof].mean()
    cluster_norm  = (cluster_means - cluster_means.min()) / \
                    (cluster_means.max() - cluster_means.min() + 1e-9)

    fig, ax = plt.subplots(figsize=(14, max(4, best_k * 1.5)))
    sns.heatmap(cluster_norm, annot=True, fmt='.2f', cmap='YlOrRd', ax=ax, linewidths=0.5)
    ax.set(title=f'Cluster Profile Heatmap (Normalised) — k={best_k}',
           xlabel='Feature', ylabel='Cluster')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=40, ha='right')
    savefig('profiling/cluster_profiles.png')

    # --- Feature Variance ---
    print('  Feature variance...')
    cluster_std = X_prof_df.groupby('cluster')[feat_cols_prof].std().mean()
    fig, ax = plt.subplots(figsize=(12, 6))
    cluster_std.sort_values(ascending=False).plot.bar(ax=ax, color=COLORS[0])
    ax.set(title='Feature Variability Across Clusters (Mean Std Dev)',
           xlabel='Feature', ylabel='Mean Std Dev')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=40, ha='right')
    savefig('profiling/feature_variance.png')

print('  Profiling done.\n')


# ─────────────────────────────────────────────────────────────
# 4. RESCHEDULE AGENT
# ─────────────────────────────────────────────────────────────
print('[2/3] RESCHEDULE AGENT ─────────────────────────────────')


def _fe_reschedule(df):
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
    df['u_mean_delta'] = grp['delta_s'].transform(
        lambda s: s.shift(1).expanding().mean().fillna(s.median()))
    df['u_std_delta']  = grp['delta_s'].transform(
        lambda s: s.shift(1).expanding().std().fillna(1.0))
    df['is_long_gap']  = (df['delta_s'] > df['delta_s'].quantile(0.75)).astype(int)

    feat_cols = ['correct','q_freq','u_freq','hour','dow',
                 'u_count','u_mean_delta','u_std_delta','is_long_gap']
    X = df[feat_cols].fillna(0)
    y = np.log1p(df['delta_s'].clip(lower=0))
    return X, y, feat_cols


df_resched = load_csv('reschedule_training.csv', nrows=80_000)

if df_resched is not None and not df_resched.empty:
    from sklearn.model_selection import train_test_split
    print('  Engineering features...')
    X_rs, y_rs, feat_cols_rs = _fe_reschedule(df_resched)
    X_tr_rs, X_te_rs, y_tr_rs, y_te_rs = train_test_split(
        X_rs, y_rs, test_size=0.2, random_state=42)

    scaler_rs = joblib.load(os.path.join(MODEL_DIR, 'reschedule/scaler_fe.pkl'))
    X_tr_rss  = scaler_rs.transform(X_tr_rs)
    X_te_rss  = scaler_rs.transform(X_te_rs)

    lgb_rs   = joblib.load(os.path.join(MODEL_DIR, 'reschedule/lgb_fe_model.pkl'))
    rf_rs    = joblib.load(os.path.join(MODEL_DIR, 'reschedule/rf_fe_best.pkl'))
    xgb_rs   = joblib.load(os.path.join(MODEL_DIR, 'reschedule/xgb_best.pkl'))
    stack_rs = joblib.load(os.path.join(MODEL_DIR, 'reschedule/stack_fe_model.pkl'))

    def _rs_predict(model, X, X_sc):
        if isinstance(model, lgb.Booster):
            return model.predict(X.values)
        if hasattr(model, 'n_features_in_') and model.n_features_in_ != X_sc.shape[1]:
            return None  # skip models with mismatched feature count
        return model.predict(X_sc)

    preds_raw = {
        'LightGBM':     _rs_predict(lgb_rs,   X_te_rs, X_te_rss),
        'RandomForest': _rs_predict(rf_rs,    X_te_rs, X_te_rss),
        'XGBoost':      _rs_predict(xgb_rs,   X_te_rs, X_te_rss),
        'Stacking':     _rs_predict(stack_rs, X_te_rs, X_te_rss),
    }
    preds = {k: v for k, v in preds_raw.items() if v is not None}
    if 'XGBoost' not in preds:
        print('  [SKIP] XGBoost: feature count mismatch (was retrained with extra feature)')

    def _reg_met(y_true, y_pred, name):
        mae  = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        ss_res = np.sum((y_true - y_pred)**2)
        ss_tot = np.sum((y_true - y_true.mean())**2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        print(f'  {name}: MAE={mae:.4f}  RMSE={rmse:.4f}  R²={r2:.4f}')
        save_metrics_row(all_metrics, 'Reschedule', name,
                         {'MAE': round(mae,4), 'RMSE': round(rmse,4), 'R2': round(r2,4)})
        return mae, rmse, r2

    results = {}
    for mname, pred in preds.items():
        results[mname] = _reg_met(y_te_rs, pred, mname)

    # --- MAE / RMSE / R² comparison ---
    print('  Plotting model comparison...')
    mnames = list(preds.keys())
    mae_vals  = [results[m][0] for m in mnames]
    rmse_vals = [results[m][1] for m in mnames]
    r2_vals   = [results[m][2] for m in mnames]

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    for ax, vals, title in zip(axes,
                                [mae_vals, rmse_vals, r2_vals],
                                ['MAE (log1p scale)', 'RMSE (log1p scale)', 'R²']):
        bars = ax.bar(mnames, vals, color=COLORS[:4], width=0.5)
        for b in bars:
            ax.text(b.get_x()+b.get_width()/2, b.get_height()+0.001,
                    f'{b.get_height():.4f}', ha='center', va='bottom', fontsize=10)
        ax.set(title=title, ylabel=title)
        ax.set_xticklabels(mnames, rotation=20, ha='right')
    fig.suptitle('Model Comparison — Reschedule Agent', fontsize=14, fontweight='bold')
    savefig('reschedule/model_comparison.png')

    # --- Predicted vs Actual ---
    print('  Predicted vs actual scatter...')
    n_m = len(preds)
    c_m = min(2, n_m); r_m = (n_m + c_m - 1) // c_m
    fig, axes = plt.subplots(r_m, c_m, figsize=(7*c_m, 6*r_m))
    ax_list = [axes] if n_m == 1 else (list(axes) if r_m == 1 else [a for row in axes for a in row])
    for ax, (mname, pred) in zip(ax_list, preds.items()):
        idx = np.random.RandomState(42).choice(len(y_te_rs), min(2000, len(y_te_rs)), replace=False)
        ax.scatter(y_te_rs.iloc[idx], pred[idx], alpha=0.3, s=8, color=COLORS[0])
        lim = [min(float(y_te_rs.min()), float(pred.min())),
               max(float(y_te_rs.max()), float(pred.max()))]
        ax.plot(lim, lim, 'r--', lw=1.5)
        mae_v  = results[mname][0]
        r2_v   = results[mname][2]
        ax.set(title=f'{mname}\nMAE={mae_v:.4f}  R²={r2_v:.4f}',
               xlabel='Actual (log1p s)', ylabel='Predicted (log1p s)')
    for ax in ax_list[n_m:]:
        ax.set_visible(False)
    n_m2 = len(preds)
    c_m2 = min(2, n_m2); r_m2 = (n_m2 + c_m2 - 1) // c_m2
    fig, axes = plt.subplots(r_m2, c_m2, figsize=(7*c_m2, 5*r_m2))
    ax_list2 = [axes] if n_m2==1 else (list(axes) if r_m2==1 else [a for row in axes for a in row])
    for ax, (mname, pred) in zip(ax_list2, preds.items()):
        residuals = y_te_rs.values - pred
        ax.hist(residuals, bins=60, color=COLORS[0], edgecolor='white', alpha=0.8)
        ax.axvline(0, color='red', ls='--', lw=1.5)
        ax.axvline(float(residuals.mean()), color='orange', ls='--', lw=1.5,
                   label=f'mean={residuals.mean():.3f}')
        ax.set(title=f'{mname} Residuals', xlabel='Residual', ylabel='Count')
        ax.legend()
    for ax in ax_list2[n_m2:]:
        ax.set_visible(Falsesiduals, bins=60, color=COLORS[0], edgecolor='white', alpha=0.8)
        ax.axvline(0, color='red', ls='--', lw=1.5)
        ax.axvline(float(residuals.mean()), color='orange', ls='--', lw=1.5,
                   label=f'mean={residuals.mean():.3f}')
        ax.set(title=f'{mname} Residuals', xlabel='Residual', ylabel='Count')
        ax.legend()
    fig.suptitle('Residual Distributions — Reschedule Agent', fontsize=14, fontweight='bold')
    savefig('reschedule/residuals.png')

    # --- Feature Importance ---
    print('  Feature importances...')
    model_list = [(n, m) for n, m in [
        ('LightGBM', lgb_rs), ('RandomForest', rf_rs),
        ('XGBoost', xgb_rs), ('Stacking', stack_rs)
    ] if n in preds]  # only show models that ran
    n_plots = len(model_list)
    cols = min(2, n_plots)
    rows = (n_plots + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(8*cols, 6*rows))
    if n_plots == 1:
        axes = [axes]
    elif rows == 1:
        axes = list(axes)
    else:
        axes = [ax for row in axes for ax in row]

    for ax, (mname, model) in zip(axes, model_list):
        try:
            if isinstance(model, lgb.Booster):
                fi = pd.Series(model.feature_importance(importance_type='gain'),
                               index=model.feature_name())
            elif hasattr(model, 'feature_importances_'):
                fi = pd.Series(model.feature_importances_, index=feat_cols_rs)
            elif hasattr(model, 'estimators_'):
                importances = []
                for est in model.estimators_:
                    if hasattr(est, 'feature_importances_'):
                        importances.append(est.feature_importances_)
                if importances:
                    fi = pd.Series(np.mean(importances, axis=0), index=feat_cols_rs)
                else:
                    ax.text(0.5, 0.5, 'N/A', ha='center', va='center', transform=ax.transAxes)
                    continue
            else:
                ax.text(0.5, 0.5, 'N/A', ha='center', va='center', transform=ax.transAxes)
                continue
            fi.sort_values().plot.barh(ax=ax, color=COLORS[1])
            ax.set(title=f'{mname} Feature Importance', xlabel='Importance')
        except Exception as e:
            ax.text(0.5, 0.5, str(e)[:80], ha='center', va='center',
                    transform=ax.transAxes, fontsize=8, wrap=True)
    # Hide unused axes
    for ax in axes[n_plots:]:
        ax.set_visible(False)
    fig.suptitle('Feature Importances — Reschedule Agent', fontsize=14, fontweight='bold')
    savefig('reschedule/feature_importance.png')

print('  Reschedule done.\n')


# ─────────────────────────────────────────────────────────────
# 5. SUMMARY TABLE — Load existing progress+motivation metrics and merge
# ─────────────────────────────────────────────────────────────
print('[3/3] SUMMARY TABLE ─────────────────────────────────────')

# Build progress metrics from the already-saved LGB model
lgb_prog = joblib.load(os.path.join(MODEL_DIR, 'progress/lgb_model.pkl'))
print('  Progress LGB best score:', dict(lgb_prog.best_score))

# Build motivation metrics from saved RF/LGB
rf_mot  = joblib.load(os.path.join(MODEL_DIR, 'motivation/rf.pkl'))
le_mot  = joblib.load(os.path.join(MODEL_DIR, 'motivation/label_encoder.pkl'))
feat_cols_mot = joblib.load(os.path.join(MODEL_DIR, 'motivation/feat_cols.pkl'))

# Quick eval of motivation RF on a test split
df_mot_eval = load_csv('motivation_training.csv', nrows=5000)
if df_mot_eval is not None:
    LEAK = {'stress_level', 'Stress_Score', 'Stress_Level'}
    num_c_m = df_mot_eval.select_dtypes(include='number').columns
    fc = [c for c in num_c_m if c not in LEAK and 'unnamed' not in c.lower()]
    target_col = 'stress_level'
    df_clean = df_mot_eval[fc + [target_col]].dropna()
    from sklearn.preprocessing import StandardScaler, LabelEncoder
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, f1_score
    y_m = LabelEncoder().fit_transform(df_clean[target_col].astype(int))
    X_m = df_clean[fc].fillna(0)
    _, X_te_m, _, y_te_m = train_test_split(X_m, y_m, test_size=0.2, random_state=42, stratify=y_m)
    sc_m = joblib.load(os.path.join(MODEL_DIR, 'motivation/scaler.pkl'))
    X_te_ms = sc_m.transform(X_te_m)
    rf_pred_m = rf_mot.predict(X_te_ms)
    mot_acc = accuracy_score(y_te_m, rf_pred_m)
    mot_f1  = f1_score(y_te_m, rf_pred_m, average='weighted', zero_division=0)
    save_metrics_row(all_metrics, 'Motivation', 'RF (eval)', {'Accuracy': round(mot_acc,4), 'F1_weighted': round(mot_f1,4)})
    print(f'  Motivation RF: acc={mot_acc:.4f}  f1={mot_f1:.4f}')

# Profiling silhouette already added above
# Reschedule metrics already added to all_metrics

summary_df = pd.DataFrame(all_metrics)
summary_path = os.path.join(OUT_DIR, 'summary/metrics_table.csv')
summary_df.to_csv(summary_path, index=False)
print(f'\n  Metrics table → {summary_path}')
print()
print(summary_df.fillna('–').to_string(index=False))

# Visual summary
fig, ax = plt.subplots(figsize=(16, max(4, len(summary_df)*0.6+2)))
ax.axis('off')
col_labels = list(summary_df.columns)
cell_text  = summary_df.fillna('–').values.tolist()
table = ax.table(cellText=cell_text, colLabels=col_labels,
                 cellLoc='center', loc='center',
                 colColours=[COLORS[0]]*len(col_labels))
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
# 6. VARIANCE-ACCURACY (motivation, fast)
# ─────────────────────────────────────────────────────────────
print('\n[Bonus] VARIANCE-ACCURACY ───────────────────────────────')
from sklearn.ensemble import RandomForestClassifier
import lightgbm as lgb

df_mot2 = load_csv('motivation_training.csv')
if df_mot2 is not None and not df_mot2.empty:
    LEAK2 = {'stress_level', 'Stress_Score', 'Stress_Level'}
    nc2 = df_mot2.select_dtypes(include='number').columns
    fc2 = [c for c in nc2 if c not in LEAK2 and 'unnamed' not in c.lower()]
    from sklearn.preprocessing import LabelEncoder, StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score
    y2_raw = LabelEncoder().fit_transform(df_mot2['stress_level'].dropna().astype(int))
    X2 = df_mot2.loc[df_mot2['stress_level'].notna(), fc2].fillna(0)
    y2 = pd.Series(y2_raw, index=X2.index)
    X_tr2, X_te2, y_tr2, y_te2 = train_test_split(X2, y2, test_size=0.2,
                                                    random_state=42, stratify=y2)
    sc2 = StandardScaler().fit(X_tr2)
    X_tr2s = sc2.transform(X_tr2)
    X_te2s  = sc2.transform(X_te2)
    n_cls2 = len(np.unique(y2))

    sizes      = [0.1, 0.25, 0.5, 0.75, 1.0]
    res_va = {'RF': [], 'LGB': []}
    for frac in sizes:
        n = max(100, int(len(X_tr2) * frac))
        idx = np.random.RandomState(42).choice(len(X_tr2), n, replace=False)
        X_s = X_tr2s[idx]; y_s = y_tr2.iloc[idx]
        rf_t = RandomForestClassifier(n_estimators=50, max_depth=8,
                                       random_state=42, n_jobs=-1).fit(X_s, y_s)
        res_va['RF'].append(accuracy_score(y_te2, rf_t.predict(X_te2s)))
        ds_t = lgb.Dataset(X_s, label=y_s.values)
        lgb_t = lgb.train({'objective':'multiclass','num_class':n_cls2,
                            'verbose':-1,'seed':42,'num_leaves':31,'num_iterations':100},
                          ds_t)
        pred_t = np.argmax(lgb_t.predict(X_te2s), axis=1)
        res_va['LGB'].append(accuracy_score(y_te2, pred_t))
        print(f'  frac={frac:.0%} ({n} samples) RF={res_va["RF"][-1]:.4f} LGB={res_va["LGB"][-1]:.4f}')

    sample_counts = [max(100, int(len(X_tr2)*f)) for f in sizes]
    fig, ax = plt.subplots(figsize=(10, 6))
    for mname, accs in res_va.items():
        ax.plot(sample_counts, accs, 'o-', lw=2, label=mname)
    ax.set(title='Accuracy vs Training Set Size — Motivation Agent',
           xlabel='Training Samples', ylabel='Test Accuracy')
    ax.legend()
    savefig('summary/variance_accuracy.png')

print('\n' + '='*60)
print(f' All remaining plots saved to {OUT_DIR}')
print('='*60 + '\n')
