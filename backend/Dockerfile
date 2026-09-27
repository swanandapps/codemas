# One image for both Railway services:
#   web    — default CMD (migrate + gunicorn)
#   worker — start command overridden to `celery -A codemas worker -B`
# Compilers/runtimes are here because run_local executes student code in the worker.
FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs g++ default-jdk-headless \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput

# gthread workers so the SSE submission stream doesn't pin a whole worker process
CMD python manage.py migrate --noinput && \
    gunicorn codemas.wsgi --bind 0.0.0.0:${PORT:-8000} --worker-class gthread --workers 2 --threads 8 --timeout 120
