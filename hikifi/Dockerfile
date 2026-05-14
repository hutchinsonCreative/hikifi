FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY requirements-runtime.txt /app/requirements-runtime.txt
RUN pip install --no-cache-dir -r /app/requirements-runtime.txt

COPY src/ /app/src/
COPY scripts/ /app/scripts/

CMD ["python", "-m", "src.main", "--config", "/app/config.yml"]
