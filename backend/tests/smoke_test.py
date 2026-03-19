"""Quick smoke test for all API endpoints."""
import urllib.request
import json
import sys

BASE = "http://localhost:8000"


def req(method, path, data=None, token=None):
    body = json.dumps(data).encode() if data else None
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = "Bearer " + token
    r = urllib.request.Request(BASE + path, body, hdrs, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read().decode()[:300]}
    except urllib.error.URLError as e:
        return {"connection_error": str(e)}


def ok(label, result, check_key=None):
    if "http_error" in result:
        print(f"FAIL [{label}] HTTP {result['http_error']}: {result.get('body','')[:120]}")
        return False
    if check_key and check_key not in result:
        print(f"FAIL [{label}] missing key '{check_key}' in {list(result.keys())}")
        return False
    val = result.get(check_key, "") if check_key else str(result)[:80]
    print(f"PASS [{label}] {check_key}={val}" if check_key else f"PASS [{label}] {val}")
    return True


# ── Health ──────────────────────────────────────────────────────────────────
ok("health", req("GET", "/health"), "status")

# ── Auth ────────────────────────────────────────────────────────────────────
reg = req("POST", "/api/v1/auth/register", {
    "name": "SmokeUser", "email": "smoke@test.com",
    "password": "smoke1234", "studyHoursPerDay": 2, "learningGoal": "Testing"
})
if "access_token" not in reg:
    reg = req("POST", "/api/v1/auth/login", {"email": "smoke@test.com", "password": "smoke1234"})

if "access_token" not in reg:
    print("FAIL [auth] could not register or login:", reg)
    sys.exit(1)

T = reg["access_token"]
print(f"PASS [auth] name={reg.get('name','?')} token={len(T)}c")

# ── Users /me ────────────────────────────────────────────────────────────────
ok("users/me", req("GET", "/api/v1/users/me", token=T), "email")

# ── Profiling ────────────────────────────────────────────────────────────────
ok("profiling/classify", req("POST", "/api/v1/profiling/classify",
    {"grades": ["A", "B"], "studyHoursPerWeek": 10, "attendanceRate": 85,
     "selfStudyHoursPerWeek": 5, "numSubjects": 4}, T), "profile_label")

# ── Motivation ───────────────────────────────────────────────────────────────
ok("motivation/classify", req("POST", "/api/v1/motivation/classify",
    {"anxiety_level": 8, "stress_level": 15}, T), "category")

# ── Progress ─────────────────────────────────────────────────────────────────
ok("progress/predict", req("POST", "/api/v1/progress/predict",
    {"difficulty": 0.6, "u_cum_acc": 0.7}, T), "correct_probability")

# ── Community ────────────────────────────────────────────────────────────────
ok("community/peers", req("GET", "/api/v1/community/peers", token=T), "peers")

# ── Group ────────────────────────────────────────────────────────────────────
ok("group/match", req("POST", "/api/v1/group/match", {"grade": "A"}, T), "group_id")

# ── Stress ───────────────────────────────────────────────────────────────────
ok("stress/log", req("POST", "/api/v1/stress/log",
    {"stress_level": 4, "sleep_hours": 7, "physical_activity": 30}, T), "msg")
ok("stress/analysis", req("GET", "/api/v1/stress/analysis", token=T), "avg_stress")
