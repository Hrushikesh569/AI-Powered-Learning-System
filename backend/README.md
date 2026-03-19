# Autonomous Multi-Agent AI Backend

Production-ready backend for adaptive student performance optimization.

## Stack
- FastAPI (REST API)
- PostgreSQL (relational DB)
- Redis (cache, pub/sub)
- Celery (background tasks)
- MLflow (model registry)
- Dockerized ML model serving
- JWT authentication

## Structure
- Modular monolith, event-driven agents
- Agents: Profiling, Schedule Generator (RL), Progress Monitor, Adaptive Rescheduler (RL), Motivation, Community, Group Matching

## Setup
1. Install Python 3.10+
2. `pip install -r requirements.txt`
3. Configure `.env` for DB, Redis, JWT
4. Run `alembic upgrade head` for migrations
5. Start with `uvicorn app.main:app --reload`

## Folders
- `app/` - FastAPI app, agents, core, db
- `ml/` - ML models, pipelines
- `docker/` - Dockerfiles for services

## Research
- See `docs/research.md` for system/ML details
