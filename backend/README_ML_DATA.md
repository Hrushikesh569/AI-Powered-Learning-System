# ML Data and Model Workflow

- Place your raw or preprocessed data files (CSV, Parquet, etc.) in:
  backend/data/

- Trained models for each agent will be saved in:
  backend/app/ml/profiling/
  backend/app/ml/schedule/
  backend/app/ml/progress/
  backend/app/ml/reschedule/
  backend/app/ml/motivation/
  backend/app/ml/community/
  backend/app/ml/group/

- You can add your data to backend/data/ and I will generate training scripts and minimal mockup models for each agent, so the backend will work end-to-end.

- For now, I will generate example training scripts using synthetic/mock data for each agent. You can later replace the data loading part with your real data.
