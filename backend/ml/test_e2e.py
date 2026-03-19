"""End-to-end smoke test: register, login, test ML endpoints."""
import requests, random, string

BASE = "http://localhost:8000"

# Register a temp test user
uid = ''.join(random.choices(string.ascii_lowercase, k=8))
reg = requests.post(f"{BASE}/api/v1/auth/register", json={
    "email": f"{uid}@test.com",
    "password": "TestPass123!",
    "full_name": "Test User"
}, timeout=10)
print(f"[{reg.status_code}] Register: {reg.text[:100]}")

# Login
login = requests.post(f"{BASE}/api/v1/auth/login", json={
    "email": f"{uid}@test.com",
    "password": "TestPass123!"
}, timeout=10)
print(f"[{login.status_code}] Login: {login.text[:150]}")

if login.status_code != 200:
    print("Cannot proceed without token"); raise SystemExit(1)

token = login.json().get("access_token", "")
headers = {"Authorization": f"Bearer {token}"}

def check(label, r):
    status = "OK" if r.status_code < 300 else "ERR"
    print(f"  [{status} {r.status_code}] {label}: {r.text[:250]}")

print("\n--- ML Agent Endpoints ---")
# Profiling classify
check("Profiling/classify", requests.post(
    f"{BASE}/api/v1/profiling/classify",
    json={"weekly_self_study_hours": 10, "attendance_percentage": 85.0,
          "class_participation": 3.0, "total_score": 75.0, "grade": 3.0,
          "study_hours": 8.0, "age": 21.0, "math_score": 78.0,
          "science_score": 72.0, "english_score": 80.0, "overall_score": 76.0},
    headers=headers, timeout=15))

# Progress predict
check("Progress/predict", requests.post(
    f"{BASE}/api/v1/progress/predict",
    json={"difficulty": 0.5, "u_cum_acc": 0.75, "u_roll5": 0.8, "u_total": 50,
          "attempt_n": 1, "q_cum_acc": 0.6, "irt_score": 0.7, "prev_correct": 1},
    headers=headers, timeout=15))

# Motivation classify
check("Motivation/classify", requests.post(
    f"{BASE}/api/v1/motivation/classify",
    json={"anxiety_level": 3, "self_esteem": 5, "mental_health_history": 0,
          "depression": 2, "headache": 1, "blood_pressure": 1,
          "sleep_quality": 4, "breathing_problem": 0, "noise_level": 2,
          "living_conditions": 3, "safety": 4, "basic_needs": 3,
          "academic_performance": 3, "study_load": 2,
          "teacher_student_relationship": 4, "future_career_concerns": 3,
          "social_support": 4, "peer_pressure": 2,
          "extracurricular_activities": 1, "bullying": 0},
    headers=headers, timeout=15))

# Motivation tips
check("Motivation/tips", requests.get(
    f"{BASE}/api/v1/motivation/tips",
    headers=headers, timeout=10))

# Progress dashboard
check("Progress/dashboard", requests.get(
    f"{BASE}/api/v1/progress/dashboard",
    headers=headers, timeout=10))

# User profile
check("Users/me", requests.get(
    f"{BASE}/api/v1/users/me",
    headers=headers, timeout=10))

print("\nSmoke test complete.")
