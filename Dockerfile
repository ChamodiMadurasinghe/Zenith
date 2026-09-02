FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir \
        "gunicorn>=22.0" \
        "flask>=3.0" \
        "apscheduler>=3.10" \
        "python-dotenv>=1.0" \
        "markdown>=3.5" \
        "Pillow>=10.0" \
        "reportlab>=4.0" \
        "num2words>=0.5" \
        "openai>=1.0" \
        "langchain>=0.3,<0.4" \
        "langchain-openai>=0.2,<0.3" \
        "langchain-google-genai>=2.0.0,<2.1.0" \
        "langchain-core>=0.3,<0.4" \
        "twilio>=9.0" \
        "python-docx>=1.1"

COPY . .

ENV HOST=0.0.0.0
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

CMD python -m gunicorn --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT:-5000} app:app
