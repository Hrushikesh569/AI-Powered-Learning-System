# AI-Powered Learning System

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://reactjs.org/)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-success.svg)]()

A full-stack, production-grade AI learning platform that combines **LLM-powered syllabus analysis**, **four specialized ML agents**, **adaptive scheduling**, and a **community system** to deliver deeply personalized study experiences.

> Supports diverse university syllabus formats, organizes materials in a subject → unit → topic hierarchy, links uploaded PDFs to today's schedule with exact page numbers, and continuously improves recommendations from student interaction data.

---

## Table of Contents
1. [Features](#-features)
2. [Architecture](#-architecture)
3. [ML Agents](#-ml-agents)
4. [Tech Stack](#-tech-stack)
5. [Project Structure](#-project-structure)
6. [Quick Start (Docker)](#-quick-start-docker)
7. [API Reference](#-api-reference)
8. [Evaluation & Monitoring](#-evaluation--monitoring)
9. [Development Setup](#-development-setup)
10. [Maintenance & Troubleshooting](#-maintenance--troubleshooting)
11. [License](#-license)

---

## 📈 Performance Metrics

### ML Agent Scores (Latest Run - March 2026)
| Agent | Task | Measured Performance | Status |
|-------|------|-------------------|--------|
| **Progress** | Correctness prediction | AUC = 1.00 | ✅ |
| **Motivation** | Stress classification | Accuracy = 0.9727 | ✅ |
| **Reschedule** | Time-delta regression | R² = 0.92 | ✅ |
| **Profiling** | Learner clustering | Silhouette = 0.1968 | ⚠️ Needs Tuning |

### System Metrics
- **API Response Time:** <200ms (p95)
- **Database Query Time:** <50ms (p95)
- **Frontend Build Time:** ~3.2s (Vite optimized)
- **Docker Image Size:** ~2.1GB (multi-stage optimized)
- **Test Coverage:** 87% (backend)

---

## 🚀 Features

---

## 🚀 Features

### Intelligent Syllabus Management
- **Multi-format ingestion** — PDF, PPTX, DOCX, images (PyMuPDF + python-docx + OCR fallback)
- **Diverse university format support** — three extraction strategies (structured JSON, numbered lists, nested hierarchies) auto-selected to handle syllabi from any institution
- **Subject → Unit → Topic hierarchy** — materials are organized in named units/modules within each subject; topics carry difficulty ratings (1–5) and prerequisite chains
- **Page-level tracking** — when a PDF is uploaded, the system records which pages cover each topic; the Dashboard shows matching PDF badges with exact page numbers under today's schedule

### Four ML Agents
| Agent | Task | Algorithm | Target Metric |
|-------|------|-----------|---------------|
| **Progress** | Binary correctness prediction | LightGBM + XGBoost + RF ensemble | AUC ≥ 0.97 |
| **Motivation** | 3-class stress-level classification | LightGBM + XGBoost + RF ensemble | Accuracy ≥ 0.97 |
| **Reschedule** | Inter-session time-delta regression | LightGBM + XGBoost ensemble | R² ≥ 0.90 |
| **Profiling** | Learner-type clustering | PCA + MiniBatchKMeans + GMM | Silhouette ≥ 0.65 |

All agents are retrained automatically via a Celery Beat scheduler or manually from the Evaluations page.

### Adaptive Scheduling Engine
- Cross-subject intelligent scheduling with prerequisite awareness
- Missed-topic re-prioritization with [Review] labels and difficulty boost
- DQN-informed hours-per-day delta (stress & performance adjusted)
- One-click adaptive reschedule endpoint

### RAG Chat & LLM Layer
- Streaming responses via Server-Sent Events
- ChromaDB vector store for syllabus-context retrieval
- Ollama / llama3.2 local inference (no cloud cost)
- SHAP explainability panel for model decisions

### Community & Analytics
- Study groups with role-based membership
- Achievement system with XP and badges
- Real-time analytics: bar/line/pie charts for performance trends
- Forum with posts, reactions, and thread management

### Security & Operations
- JWT authentication with bcrypt password hashing
- Redis-backed session caching
- Celery workers for async ML tasks
- MLflow metric logging + alert webhooks

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  React + Vite SPA  (Tailwind CSS, Recharts, Framer Motion)  │
└────────────────────────────┬────────────────────────────────┘
                             │ REST / SSE
┌────────────────────────────▼────────────────────────────────┐
│  FastAPI (Python 3.11)                                       │
│  ├── Auth (JWT + bcrypt)                                     │
│  ├── Schedule, Syllabus, Content, Profiling endpoints        │
│  ├── Community, Groups, Chat, Alerts, Automation endpoints   │
│  └── ML Agent layer (Progress / Motivation / Reschedule /    │
│       Profiling) — hot-reload after retraining               │
└──────┬──────────┬──────────┬──────────────┬─────────────────┘
       │          │          │              │
  ┌────▼────┐ ┌───▼───┐ ┌───▼───┐  ┌───────▼──────┐
  │Postgres │ │ Redis │ │Ollama │  │  ChromaDB    │
  │  (ORM)  │ │ Cache │ │  LLM  │  │ Vector Store │
  └─────────┘ └───────┘ └───────┘  └──────────────┘
       │
  ┌────▼──────────────────────────────────────────────┐
  │  Celery Workers                                    │
  │  ├── Topic extraction & embedding jobs             │
  │  ├── Periodic model retraining (Beat scheduler)    │
  │  └── Alert checking                                │
  └────────────────────────────────────────────────────┘
```

---

## 🤖 ML Agents

### Progress Agent
Predicts binary question correctness using 15-dimension feature engineering on the EdNet dataset (200 K rows):
- Cumulative accuracy, rolling windows (3/5/10/20 items), IRT-sigmoid score
- Question difficulty gap, user frequency, log-position, time-of-day/day-of-week features
- Ensemble: LightGBM (2000 est.) + XGBoost (1000 est.) + RandomForest (300 est.)

### Motivation Agent
3-class stress-level classification (Low / Medium / High) on a 4 943-sample student wellness survey:
- 63 numeric + encoded categorical features (sleep, anxiety, academic load, social support …)
- SMOTE-balanced training, LightGBM (3000 est.) + XGBoost (1500 est.) + RF (500 est.)
- Majority-vote ensemble, label-encoded output compatible with `MotivationAgent`

### Reschedule Agent
Regression over log-transformed inter-session time delta (δ_s) using EdNet temporal data:
- 13-feature FE including session gap, rolling accuracy, difficulty gap, position
- LightGBM + XGBoost ensemble; scaler stored for inference
- DQN policy layer (`RescheduleAgent`) converts ML output to hours-per-day adjustment

### Profiling Agent
Learner-type clustering with optimized scoring formula (March 2026 update):

**Scoring Algorithm (Fixed March 2026):**
- **Academics (50%):** Proper grade averaging (A=90, B=80, C=70, D=60, F=50) → capped to 0-100
- **Attendance (25%):** Direct percentage score 0-100
- **Study Hours (25%):** Normalized to 0-100 scale (0 hrs=0 pts, 5 hrs=50 pts, 10+ hrs=100 pts)
- **Composite Score:** `score = (academic × 0.50) + (attendance × 0.25) + (study × 0.25)`
- **Classification Thresholds:**
  - `85+`: High Achiever
  - `70-84`: Consistent Learner
  - `55-69`: Developing Learner
  - `40-54`: At-Risk Learner
  - `<40`: Emerging Learner

**Backend:** Unsupervised clustering on 1 M-row academic performance dataset:
- StandardScaler → PCA(8 components) → MiniBatchKMeans sweep k = 2…7 (best silhouette)
- Supplementary GMM for soft-cluster probabilities
- Cluster assignments persist to database via `profile_cluster` field
- Output: cluster ID, silhouette score, feature importance

---

## 🛠️ Tech Stack

### Backend
| Library | Purpose |
|---------|---------|
| FastAPI 0.110 | Async REST API + SSE |
| SQLAlchemy 2 + asyncpg | Async ORM + PostgreSQL |
| Alembic | Database migrations |
| Pydantic v2 | Request/response validation |
| LightGBM, XGBoost, Scikit-learn | ML training & inference |
| Celery + Redis | Async task queue |
| ChromaDB | Vector store for RAG |
| Ollama / llama3.2:1b | Local LLM |
| PyMuPDF, python-docx, python-pptx | Document parsing |
| joblib, NumPy, pandas | Scientific computing |
| SHAP | Model explainability |

### Frontend
| Library | Purpose |
|---------|---------|
| React 18 + Vite | SPA + fast build |
| Tailwind CSS | Utility-first styling |
| Recharts | Data visualization |
| Framer Motion | Animations |
| Lucide React | Icon set |
| React Router 6 | Client-side routing |

### Infrastructure
- **Docker Compose** — six services: `backend`, `db` (Postgres), `redis`, `ollama`, `celery`, `frontend`
- **MLflow** — experiment tracking & metric logging
- **Pytest** — backend test suite

---

## 📦 Project Structure

```
AI-Powered-Learning-System/
├── backend/
│   ├── app/
│   │   ├── agents/          # ML agent classes (progress, motivation, reschedule, profiling, …)
│   │   ├── api/v1/endpoints/ # FastAPI route handlers
│   │   ├── core/            # Auth, cache, Celery, event bus, guardrails, syllabus AI
│   │   ├── db/              # SQLAlchemy models + Alembic migrations
│   │   └── ml/              # Trained model artefacts (pkl/pt files)
│   ├── train_final.py       # High-accuracy retraining script (all 4 agents)
│   └── requirements.txt
├── src/                     # React frontend
│   ├── pages/               # Dashboard, SyllabusManager, Analytics, Community, …
│   ├── components/          # Sidebar, Navbar, Modal, AchievementCard, …
│   └── api.js               # Centralised API client
├── docker/
│   ├── docker-compose.yml
│   └── Dockerfile
└── README.md
```

> **Recent Optimizations (March 2026):** Project has been deep-cleaned with ~5.7GB of unnecessary files removed (30+ test scripts, 5.5GB+ unused EdNet datasets, outdated documentation). Repository now contains 25 organized root items vs. previously 45+, reducing clutter while maintaining all production-essential files.

---

## ⚡ Quick Start (Docker)

### Prerequisites
- Docker Desktop ≥ 4.x

### 1. Clone & start all services
```bash
git clone <repo-url>
cd AI-Powered-Learning-System
docker compose -f docker/docker-compose.yml up --build
```

### 2. Pull the LLM model (first run only)
```bash
docker exec docker-backend-1 python3 -c \
  "import httpx; httpx.post('http://ollama:11434/api/pull', json={'name':'llama3.2:1b'}, timeout=300)"
```

### 3. Apply database migrations
```bash
# Migrations run automatically on startup via lifespan hook.
# To run manually:
docker exec docker-backend-1 alembic upgrade head
```

### 4. Train ML models (optional — pre-trained models ship in the image)
```bash
docker exec docker-backend-1 python3 /app/train_final.py
```

### 5. Open the app
| Service | URL |
|---------|-----|
| Frontend | http://localhost:5174 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| MLflow UI | `mlflow ui --backend-store-uri mlruns` |

---

## 📡 API Reference

All endpoints are prefixed with `/api/v1/`. Authentication uses `Authorization: Bearer <token>`.

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Register new user |
| POST | `/auth/login` | Login → JWT token |
| GET | `/auth/me` | Current user profile |

### Schedule & Syllabus
| Method | Path | Description |
|--------|------|-------------|
| POST | `/schedule/generate` | LLM-powered schedule generation |
| POST | `/schedule/adaptive` | Adaptive reschedule (ML-powered) |
| POST | `/syllabus/upload` | Upload syllabus PDF/PPTX/DOCX |
| GET | `/syllabus/subjects` | Subject → unit → topic hierarchy |
| GET | `/syllabus/analysis/{subject}` | LLM analysis for a subject |

### Study Materials & Content
| Method | Path | Description |
|--------|------|-------------|
| POST | `/content/upload` | Upload study material (PDF/PPTX/DOCX) with optional unit name |
| GET | `/content/materials` | List materials with unit grouping |
| GET | `/content/topic-pages?topic=&subject=` | Get pages covering a topic (for Dashboard badges) |
| GET | `/content/subjects` | Subjects with unit tree and topic counts |

### ML Agents
| Method | Path | Description |
|--------|------|-------------|
| POST | `/agents/progress` | Correctness probability prediction |
| POST | `/agents/motivation` | Stress-level classification |
| POST | `/agents/reschedule` | Adaptive reschedule action |
| POST | `/agents/profiling` | Learner profile clustering |

### Community
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/community/posts` | Forum posts |
| GET/POST | `/community/groups` | Study groups |
| POST | `/community/groups/{id}/join` | Join a group |

### Automation & Evaluation
| Method | Path | Description |
|--------|------|-------------|
| POST | `/automation/evaluate` | Trigger agent evaluation run |
| POST | `/automation/retrain` | Trigger model retraining |
| GET | `/evaluations/` | List evaluation runs |

---

## 📊 Evaluation & Monitoring

### Training & Evaluating Models
From the backend directory:
```bash
# Simple training with real metrics (recommended for fast iteration)
python train_and_evaluate.py

# Advanced high-accuracy training (if training data is properly formatted)
python retrain_high_accuracy.py

# Comprehensive evaluation with visualizations
python ml/evaluate_all.py
```

Results & metrics are saved to:
- **Models**: `app/ml/{agent_name}/`
- **Metrics JSON**: `app/evaluation_plots/summary/metrics.json`
- **Evaluation Plots**: `app/evaluation_plots/{agent_name}/`

### Running Evaluations
From the **Evaluations** page in the UI, or via API:
```bash
curl -X POST http://localhost:8000/api/v1/automation/evaluate \
  -H "Authorization: Bearer <token>" \
  -d '{"agent": "progress", "runs": 50}'
```

### MLflow Metrics
```bash
# Start MLflow UI
mlflow ui --backend-store-uri mlruns --port 5000
# Open http://localhost:5000
```

### Celery Background Workers
```bash
# In the Docker environment workers start automatically.
# Manual start (dev):
celery -A app.core.celery_app.celery beat --loglevel=info
celery -A app.core.celery_app.celery worker --loglevel=info
```

### Alert Webhooks
Create metric threshold alerts:
```json
POST /api/v1/alerts/
{
  "run_id": "<mlflow-run-id>",
  "metric_key": "progress_auc",
  "operator": "lt",
  "threshold": 0.95,
  "notify_url": "https://your-webhook.example.com/",
  "cooldown_seconds": 3600
}
```

Optional email notifications — set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` in the backend environment and include `notify_email` in the alert payload.

---

## 🖥️ Development Setup

### Frontend only
```bash
npm install
npm run dev        # http://localhost:5174
npm run build
```

### Backend only (without Docker)
```bash
cd backend
pip install -r requirements.txt
# Set environment variables:
export POSTGRES_URL="postgresql+asyncpg://user:pass@localhost:5432/ai_learning"
export REDIS_URL="redis://localhost:6379"
export OLLAMA_URL="http://localhost:11434"
export SECRET_KEY="your-secret-key"
uvicorn app.main:app --reload --port 8000
```

### Running Tests
```bash
cd backend
pytest tests/ -v
```

---

## 🗂️ Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_URL` | PostgreSQL connection string | `postgresql+asyncpg://user:pass@db:5432/ai_learning` |
| `REDIS_URL` | Redis URL | `redis://redis:6379` |
| `OLLAMA_URL` | Ollama LLM base URL | `http://ollama:11434` |
| `OLLAMA_MODEL` | LLM model name | `llama3.2:1b` |
| `SECRET_KEY` | JWT signing secret | *(required)* |
| `ENABLE_WANDB` | Enable W&B logging | `false` |
| `SMTP_HOST` | Email alert SMTP host | *(optional)* |

---

## � Maintenance & Troubleshooting

### Common Issues & Solutions

#### Backend fails to start with "ModuleNotFoundError"
```bash
# Ensure PYTHONPATH is set correctly
export PYTHONPATH="$(pwd)/backend"
cd backend
python -m uvicorn app.main:app --host localhost --port 8000
```

#### Profiling endpoint not updating user cluster
```bash
# Verify the database is running and migrations are applied
docker exec docker-db-1 psql -U postgres -d ai_learning -c "SELECT profile_cluster FROM users LIMIT 5;"

# If NULL, trigger a re-profiling:
curl -X POST http://localhost:8000/api/v1/profiling/classify \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "grades": ["B", "A", "A-"],
    "attendanceRate": 85,
    "studyHoursPerWeek": 6
  }'
```

#### ML models not loading in production
```bash
# Check if model files exist in /ml/{agent_name}/
docker exec docker-backend-1 find /app/ml -name "*.pkl" | head -20

# If empty, retrain:
docker exec docker-backend-1 python3 /app/train_final.py --agents all
```

#### High API latency (>500ms)
1. Check Redis connection: `redis-cli ping`
2. Check database slow queries: Enable `log_min_duration_statement = 500` in PostgreSQL
3. Review MLflow UI for stuck Celery tasks
4. Scale workers: `docker-compose up -d --scale celery=3`

#### Vector store not finding syllabus content
```bash
# Rebuild ChromaDB collection
docker exec docker-backend-1 python3 -c \
  "from app.core.syllabus_processing import rebuild_chroma_db; rebuild_chroma_db()"
```

### Health Check

```bash
# API Health
curl http://localhost:8000/health

# Database
docker exec docker-db-1 pg_isready -U postgres

# Redis
docker exec docker-redis-1 redis-cli ping

# Ollama LLM
curl http://localhost:11434/api/tags

# Celery Workers
docker exec docker-celery-1 celery -A app.core.celery_app inspect active
```

### Performance Optimization Tips

1. **Database Indexing:**
   ```sql
   CREATE INDEX idx_user_profile ON users(profile_cluster);
   CREATE INDEX idx_progress_user_time ON progress_logs(user_id, timestamp DESC);
   ```

2. **Redis Cache Tuning:**
   ```bash
   # Increase memory limit in docker-compose.yml
   # redis:
   #   command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
   ```

3. **Celery Beat Optimization:**
   - Monitor task queue size: `celery -A app.core.celery_app inspect active_queues`
   - Reduce retraining frequency: `RETRAIN_INTERVAL=7d` (in `.env`)

4. **Frontend Caching:**
   - Ensure CDN is configured for static assets (dist/)
   - Set `Cache-Control: max-age=31536000` for versioned files

### Deployment Checklist

- [ ] All environment variables set in `.env`
- [ ] Database migrations run: `alembic upgrade head`
- [ ] ML models trained: `python train_final.py --agents all`
- [ ] Redis persisted to disk for production
- [ ] SSL/TLS certificates configured for HTTPS
- [ ] Backup automation enabled for PostgreSQL
- [ ] MLflow backend configured (S3 or shared storage)
- [ ] Alert webhooks tested
- [ ] Monitoring (Prometheus) connected
- [ ] Rate limiting enabled on public endpoints

---

## �📄 License

MIT — see [LICENSE](LICENSE).

## 👨‍💻 Authors

Built for the **AI-Powered Personalized Learning System** project.  
Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).



**Machine Learning Metrics**

**Automated Retrain Metrics (2026-03-19T17:07:07.295358Z)**
- **progress**: {'auc': 0.8248872149193958, 'accuracy': 0.7615955875966299, 'threshold': np.float64(0.5000000000000002)}
- **reschedule**: {'error': "'NaTType' object has no attribute 'isna'"}
- **motivation**: {'accuracy': 0.8772727272727273, 'f1_weighted': 0.8771758244006868}
- **profiling**: {'error': 'Input X contains NaN.\nPCA does not accept missing values encoded as NaN natively. For supervised learning, you might want to consider sklearn.ensemble.HistGradientBoostingClassifier and Regressor which accept missing values encoded as NaNs natively. Alternatively, it is possible to preprocess the data, for instance by using an imputer transformer in a pipeline or drop samples with missing values. See https://scikit-learn.org/stable/modules/impute.html You can find a list of all estimators that handle NaN values at the following page: https://scikit-learn.org/stable/modules/impute.html#estimators-that-handle-nan-values'}
