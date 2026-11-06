# syntax=docker/dockerfile:1.7
# API, worker and scheduler share this image (build context: the repository root):
#   docker build -f apps/api/Dockerfile -t pilao-api .
#   api:       (default command) uvicorn on port 8000
#   worker:    rq worker -u "$REDIS_URL" default
#   scheduler: rq cron app/workers/cron.py -u "$REDIS_URL"
#   release:   alembic upgrade head   (once per deployment, before the new api starts)
#
# Ubuntu 24.04 LTS: Python 3.12, and the LibreOffice 24.2 the PDF export is tested with.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/bin/python3.12

# Optional extra certificate authority (a proxy that only allows HTTPS), never stored in
# the image:  docker build --secret id=extra_ca,src=/path/ca-bundle.crt ...
# Packages: OCR of scanned DCE (French), PDF export, Liberation fonts (Arial metrics).
RUN --mount=type=secret,id=extra_ca \
    CA=""; if [ -f /run/secrets/extra_ca ]; then \
        sed -i 's#http://#https://#g' /etc/apt/sources.list.d/ubuntu.sources; \
        install -m 644 /run/secrets/extra_ca /tmp/extra_ca.crt; \
        CA="-o Acquire::https::CaInfo=/tmp/extra_ca.crt"; \
    fi; \
    apt-get $CA update \
    && apt-get $CA install -y --no-install-recommends \
        ca-certificates python3.12 python3.12-venv \
        tesseract-ocr tesseract-ocr-fra libreoffice-writer-nogui libreoffice-calc-nogui \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/* /tmp/extra_ca.crt

RUN --mount=type=secret,id=extra_ca \
    if [ -f /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    python3.12 -m venv /opt/uv && /opt/uv/bin/pip install --no-cache-dir uv==0.11.32 \
    && ln -s /opt/uv/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN --mount=type=secret,id=extra_ca \
    if [ -f /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv sync --frozen --no-dev --no-install-project

COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
COPY apps/api/app ./app
COPY prompts ./prompts
COPY schemas ./schemas

# LITELLM_LOCAL_MODEL_COST_MAP: the price table shipped with LiteLLM, no download at start.
ENV PATH="/app/.venv/bin:$PATH" \
    PROMPTS_DIR=/app/prompts \
    HOME=/home/pilao \
    LITELLM_LOCAL_MODEL_COST_MAP=True

RUN useradd --create-home --uid 10001 pilao \
    && install -d -o pilao -g pilao -m 700 /data/files  # STORAGE_BACKEND=disk (ADR-033)
USER pilao
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
