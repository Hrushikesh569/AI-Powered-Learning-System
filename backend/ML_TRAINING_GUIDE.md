# ML Training & Evaluation Guide

## Quick Start

### Train High-Performance Models
```bash
cd backend
python retrain_high_accuracy.py
```
**What it does:**
- Trains all 5 ML agents with advanced feature engineering
- Uses ensemble methods (LightGBM + XGBoost) for best accuracy
- Applies SMOTE for handling class imbalance
- Targets: AUC ≥ 0.97, Accuracy ≥ 0.97, R² ≥ 0.95, Silhouette ≥ 0.90
- Saves models to `app/ml/{agent}/`
- Generates performance metrics JSON
- Creates evaluation plots in `app/evaluation_plots/`

### Evaluate All Models
```bash
cd backend
python ml/evaluate_all.py
```
**What it does:**
- Comprehensive evaluation of all trained models
- Generates paper-quality evaluation plots (150 DPI)
- Creates confusion matrices, ROC curves, performance summaries
- Outputs metrics to `app/evaluation_plots/summary/metrics.json`

## File Structure

| File | Purpose | Use Case |
|------|---------|----------|
| `retrain_high_accuracy.py` | Advanced training pipeline | **PRIMARY** - Use for best results |
| `ml/evaluate_all.py` | Comprehensive evaluation | Run after training to get metrics |
| `ml/{agent}/train_*.py` | Individual agent trainers | Low-level training (called by above) |

## Target Metrics

Each agent aims for:
- **Progress**: ROC-AUC ≥ 0.97
- **Motivation**: Accuracy ≥ 0.97
- **Reschedule**: R² ≥ 0.95
- **Profiling**: Silhouette Score ≥ 0.90

## Output Files

After running `retrain_high_accuracy.py`:
- Models: `app/ml/{profiling,schedule,progress,reschedule,motivation}/`
- Metrics: `app/evaluation_plots/summary/metrics.json`
- Plots: `app/evaluation_plots/{agent}/`

## Notes
- Both scripts now use relative paths (work in local dev environment)
- Training takes 10-30 minutes depending on data size
- Requires: pandas, scikit-learn, lightgbm, xgboost, imblearn, matplotlib, seaborn
