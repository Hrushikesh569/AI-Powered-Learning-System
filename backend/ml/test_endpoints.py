"""Quick smoke test of key ML API endpoints."""
import requests

BASE = "http://localhost:8000"

def check(label, r):
    print(f"[{r.status_code}] {label}: {r.text[:200]}")

# Health
check("Health", requests.get(f"{BASE}/health", timeout=5))

# Profiling classify
check("Profiling classify", requests.post(
    f"{BASE}/api/v1/profiling/classify",
    json={"weekly_self_study_hours": 10, "attendance_percentage": 85.0,
          "class_participation": 3, "total_score": 75.0, "grade": 3, "study_hours": 8},
    timeout=10))

# Progress predict
check("Progress predict", requests.post(
    f"{BASE}/api/v1/progress/predict",
    json={"difficulty": 0.5, "u_cum_acc": 0.75, "u_roll5": 0.8, "u_total": 50,
          "attempt_n": 1, "q_cum_acc": 0.6, "irt_score": 0.7, "prev_correct": 1},
    timeout=10))

# Profiling label (label the profiling output)
check("Profiling label", requests.post(
    f"{BASE}/api/v1/profiling/label",
    json={"cluster": 0},
    timeout=10))
