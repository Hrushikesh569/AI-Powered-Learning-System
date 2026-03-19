# Backend Dockerfile
FROM python:3.11-slim

# System dependencies:
#   - gcc/g++/libgomp1: LightGBM, XGBoost
#   - libpq-dev: psycopg2
#   - curl: used by the Ollama healthcheck in docker-compose
#   - tesseract-ocr: OCR engine used by pytesseract for scanned PDFs/images
#   - poppler-utils: pdf2image (PDF → image conversion for OCR fallback)
#   - libjpeg-dev / zlib1g-dev: Pillow image support
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libgomp1 libpq-dev curl \
    tesseract-ocr tesseract-ocr-eng \
    poppler-utils \
    libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (app/ml/ contains trained model pkl files)
COPY ./app ./app

# Copy alembic config
COPY alembic.ini ./alembic.ini

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
