Backend data pipelines and outputs

Structure under `backend/data`:

- `raw/`: source uploaded datasets (preserved)
- `processed/`: outputs of ingestion and intermediate tables (created by data engineering)
- `generated/`: derived features (item difficulty, session-time, advanced IRT/mastery)
- `final_training/`: per-agent training CSVs used for model training

Workflows
- Data engineering: `backend/data/data_engineering/run.py` — ingests `raw/` CSVs and writes `processed/interactions.csv` and feature CSVs under `generated/`.
- Advanced features: part of data engineering; generates `generated/advanced_irt_item.csv`, `generated/advanced_irt_user.csv`, and `generated/user_mastery.csv`.
- Agent datasets: `backend/data/agent_datasets/run.py` — consumes `processed/` and `generated/` and writes per-agent CSVs into `final_training/` (`profiling_training.csv`, `progress_training.csv`, `motivation_training.csv`, `reschedule_training.csv`).

Notes
- The scripts are robust and will create empty CSVs if source signals are missing; inspect `raw/` to ensure required inputs are present.
- Advanced features are simple, reproducible approximations (log-odds difficulty, user ability, EMA mastery) — replace with stronger models as needed.

Usage

Run end-to-end:

```bash
python backend/data/data_engineering/run.py
python backend/data/agent_datasets/run.py
```

After this, final per-agent CSVs are in `backend/data/final_training/`.
