# Weather → S3 job for AWS ECS on Fargate (one-shot scheduled task).
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    S3_BUCKET_NAME=wroclaw-weather-data-snisarenko \
    S3_KEY_PREFIX=weather/wroclaw/

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lambda_function.py .

USER app

# Override S3_BUCKET_NAME / S3_KEY_PREFIX on the ECS task definition if needed.
CMD ["python", "lambda_function.py"]
