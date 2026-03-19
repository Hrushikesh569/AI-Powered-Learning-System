# Local Development Setup for Backend

## Prerequisites
- Python 3.10+
- PostgreSQL (running locally)
- Redis (running locally)

## 1. Clone the repository
```
git clone <repo-url>
cd AI-Powered-Learning-System/backend
```

## 2. Create and activate a virtual environment
```
python -m venv venv
venv\Scripts\activate  # On Windows
# Or
source venv/bin/activate  # On Mac/Linux
```

## 3. Install dependencies
```
pip install -r requirements.txt
```

## 4. Configure environment variables
- Copy `.env.example` to `.env` and edit as needed:
```
cp .env.example .env  # On Mac/Linux
copy .env.example .env  # On Windows
```
- Update `POSTGRES_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, and `SECRET_KEY` in `.env`.

## 5. Start PostgreSQL and Redis locally
- Ensure PostgreSQL is running and a database is created matching your `.env` settings.
- Ensure Redis is running on the default port (6379).

## 6. Run database migrations
```
alembic upgrade head
```

## 7. Start the FastAPI backend
```
uvicorn app.main:app --reload
```

## 8. Start Celery worker (in a new terminal)
```
celery -A app.core.automation.celery_app worker --loglevel=info
```
You can also run Celery Beat to schedule periodic tasks (alerts checks, retrain jobs):

```bash
# start beat in a separate terminal
celery -A app.core.celery_app.celery beat --loglevel=info

# then start a worker in another terminal
celery -A app.core.celery_app.celery worker --loglevel=info
```

Or run both in one process for development (not recommended for production):

```bash
celery -A app.core.celery_app.celery worker -B --loglevel=info
```

## 9. (Optional) Start MLflow server
```
mlflow ui --backend-store-uri mlruns
```

---

# Local Development Setup for Frontend

## 1. Install dependencies
```
npm install
```

## 2. Start the frontend
```
npm run dev
```

- Open http://localhost:5173

---

# Troubleshooting
- If you encounter connection errors, check your PostgreSQL and Redis services.
- For Windows, ensure ports 5432 (Postgres) and 6379 (Redis) are not blocked.
- For any Python errors, ensure your virtual environment is activated.
