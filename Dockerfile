FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home appuser && mkdir -p logs data/cache && chown -R appuser logs data/cache
USER appuser

EXPOSE 8080
# One process with many threads: sessions and caches live in memory (use Redis to run several processes/instances).
# Streaming responses need a threaded worker and no request timeout cut-off mid-stream.
CMD gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --threads ${THREADS:-16} --timeout 120 --access-logfile -
