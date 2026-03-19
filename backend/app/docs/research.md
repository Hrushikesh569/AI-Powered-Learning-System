# Research System Design

## Agents
- User Profiling: KMeans/GMM clustering
- Schedule Generator: RL (DQN/PPO)
- Progress Monitor: Random Forest/XGBoost/Isolation Forest
- Adaptive Rescheduler: RL policy update
- Motivation: Logistic Regression/Random Forest/XGBoost
- Community: Embedding, cosine similarity, GNN (optional)
- Group Matching: Hierarchical/KMeans clustering

## MDP Formulation
- State: S = {profile, stress, performance, deadlines}
- Action: A = time allocation
- Reward: R = ΔPerformance − λ·ΔStress

## Data Pipeline
- Ingestion, validation, feature engineering, versioning

## Model Serving
- MLflow registry, Dockerized endpoints

## Security & Ethics
- GDPR/FERPA, bias mitigation, SHAP explainability
