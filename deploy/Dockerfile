# =============================================================================
# LeAgent Dockerfile - Multi-stage production build
# Build context: repository root (see deploy/docker-compose.yml).
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies and build wheel
# -----------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/pyproject.toml backend/README.md ./
COPY backend/leagent/ leagent/
COPY backend/leagent_core/ leagent_core/
COPY backend/alembic.ini ./
COPY backend/alembic/ alembic/

RUN pip install --upgrade pip wheel setuptools && \
    pip install -e ".[ocr,browser]" || pip install -e ".[ocr]" || pip install -e .

RUN playwright install chromium && \
    playwright install-deps chromium || true

# -----------------------------------------------------------------------------
# Stage 2: Production - Minimal runtime image
# -----------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS production

LABEL maintainer="Cheng Yuanqi <vixues@gamil.com>" \
      version="0.1.0" \
      description="LeAgent - Intelligent Office Agent Platform"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_HOME=/app \
    APP_USER=leagent \
    APP_UID=1000 \
    APP_GID=1000

WORKDIR $APP_HOME

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libmagic1 \
    poppler-utils \
    tesseract-ocr \
    libreoffice-writer-nogui \
    libreoffice-calc-nogui \
    fonts-dejavu-core \
    fonts-liberation \
    fonts-wqy-microhei \
    curl \
    netcat-openbsd \
    supervisor \
    tini \
    # Playwright/Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

RUN groupadd --gid $APP_GID $APP_USER && \
    useradd --uid $APP_UID --gid $APP_GID --shell /bin/bash --create-home $APP_USER

COPY --from=builder /opt/venv /opt/venv

COPY --from=builder /root/.cache/ms-playwright /home/$APP_USER/.cache/ms-playwright
RUN chown -R $APP_USER:$APP_USER /home/$APP_USER/.cache || true

COPY --chown=$APP_USER:$APP_USER --from=builder /build/leagent /app/leagent
COPY --chown=$APP_USER:$APP_USER --from=builder /build/leagent_core /app/leagent_core
COPY --chown=$APP_USER:$APP_USER --from=builder /build/alembic /app/alembic
COPY --chown=$APP_USER:$APP_USER --from=builder /build/alembic.ini /app/alembic.ini
COPY --chown=$APP_USER:$APP_USER --from=builder /build/pyproject.toml /app/pyproject.toml
COPY --chown=$APP_USER:$APP_USER --from=builder /build/README.md /app/README.md

RUN mkdir -p \
    /app/data \
    /app/logs \
    /app/uploads \
    /app/cache \
    /app/tmp \
    && chown -R $APP_USER:$APP_USER /app

COPY deploy/supervisord.conf /etc/supervisor/conf.d/leagent.conf
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

USER $APP_USER

ENTRYPOINT ["tini", "--", "/entrypoint.sh"]
CMD ["server"]

# -----------------------------------------------------------------------------
# Stage 3: Development - With dev tools and hot reload
# -----------------------------------------------------------------------------
FROM production AS development

USER root

RUN pip install -e ".[dev]" || true

USER $APP_USER

ENV LEAGENT_DEBUG=true \
    LEAGENT_LOG_LEVEL=DEBUG

CMD ["uvicorn", "leagent.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# -----------------------------------------------------------------------------
# Stage 4: OCR - With full OCR dependencies (PaddleOCR)
# -----------------------------------------------------------------------------
FROM production AS ocr

USER root

RUN pip install paddlepaddle paddleocr || true

USER $APP_USER
