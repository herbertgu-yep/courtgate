FROM python:3.11-slim

WORKDIR /app

# 先装依赖利用层缓存
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
COPY ui ./ui

EXPOSE 8000

# Web 用 gunicorn+uvicorn worker；worker/beat/migrate 在 compose 里覆盖 command
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8000"]
