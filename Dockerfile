FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "gunicorn>=22.0" "flask>=3.0"

COPY . .

ENV HOST=0.0.0.0
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

CMD python -m gunicorn --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT:-5000} app:app
