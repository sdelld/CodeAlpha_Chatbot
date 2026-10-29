FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home appuser && mkdir -p logs && chown appuser logs
USER appuser

EXPOSE 8080
# --preload trains the model once in the master process; workers share it.
CMD gunicorn app:app --preload --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY:-2} --threads 4 --access-logfile -
