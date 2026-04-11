FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev python3-pip curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN python3.11 -m venv /opt/venv
ENV PATH="/opt/venv/bin:/usr/local/nvidia/bin:/usr/local/cuda/bin:$PATH"

WORKDIR /app

COPY backend/pyproject.toml ./
COPY backend/ ./backend/

RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

RUN useradd -r -s /usr/sbin/nologin appuser && \
    mkdir -p /app/models /app/replays && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
