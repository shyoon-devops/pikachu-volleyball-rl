FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    MPLCONFIGDIR=/tmp/matplotlib

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev python3-pip curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN python3.11 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN useradd -r -s /usr/sbin/nologin appuser

WORKDIR /app

# Layer 1: Install dependencies only (cached unless pyproject.toml changes)
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir tomli && \
    python -c "import tomli; f=open('pyproject.toml','rb'); deps=tomli.load(f)['project']['dependencies']; f.close(); print('\n'.join(deps))" > /tmp/requirements.txt && \
    pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Layer 2: Install package (fast, no deps to resolve)
COPY backend/ ./backend/
RUN pip install --no-cache-dir --no-deps .

RUN mkdir -p /app/models /app/replays /tmp/matplotlib && \
    chown -R appuser:appuser /app /tmp/matplotlib

USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
