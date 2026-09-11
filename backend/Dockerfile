FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads/documents uploads/profiles datasets ml_models logs

EXPOSE 8000

# Single worker: WebSocket connection state and the APScheduler jobs are
# in-process. Scaling out requires Redis pub/sub and a single scheduler.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
