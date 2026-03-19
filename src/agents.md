# AI Agents and ML Techniques

## 1. User Profiling Agent
- **ML:** K-Means, GMM (clustering)
- **API:** `/profiling/label`
- **Frontend:** Profiling, Profile pages

## 2. Learning Schedule Generator Agent
- **ML:** Deep Q-Network (DQN), PPO (RL)
- **API:** `/schedule/generate`
- **Frontend:** Dashboard, Schedule

## 3. Progress Monitoring Agent
- **ML:** Random Forest, XGBoost, Isolation Forest (regression/anomaly)
- **API:** `/progress/log`, `/progress/predict`
- **Frontend:** Dashboard, Analytics

## 4. Adaptive Rescheduling Agent
- **ML:** RL policy update (DQN/PPO)
- **API:** `/schedule/generate` (triggered adaptively)
- **Frontend:** Dashboard (reschedule modal)

## 5. Feedback & Motivation Agent
- **ML:** Logistic Regression, Random Forest, XGBoost (classification)
- **API:** `/motivation/log`, `/motivation/classify`
- **Frontend:** MotivationTips, Dashboard

## 6. Community Interaction Agent
- **ML:** Embedding, Cosine Similarity, GNN (optional)
- **API:** `/community/peers`
- **Frontend:** Community, Profile

## 7. Group Matching Agent
- **ML:** Hierarchical Clustering, K-Means, Constraint Matching
- **API:** `/group/match`
- **Frontend:** Community, Group, Dashboard

---

All endpoints are available via `agentAPI` in `src/api.js` for easy integration in React components.
