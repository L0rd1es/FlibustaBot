# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data

RUN groupadd --gid 1000 app \
  && useradd --uid 1000 --gid app --create-home --shell /bin/bash app \
  && mkdir -p /app/data \
  && chown -R app:app /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app config.py main.py ./
COPY --chown=app:app handlers ./handlers
COPY --chown=app:app services ./services
COPY --chown=app:app utils ./utils

USER app

CMD ["python", "main.py"]
