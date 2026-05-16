# ── Stage 1: builder ──────────────────────────────────────────────────────────
# Install all Python dependencies into a clean prefix so we can copy only
# the compiled packages into the final image (keeps the image smaller).
FROM python:3.12-slim AS builder

# System deps needed to compile mysqlclient and other C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    pkg-config \
    default-libmysqlclient-dev \
    libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /install

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --prefix=/install/packages --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim

# Runtime system libs only (no compilers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled packages from builder
COPY --from=builder /install/packages /usr/local

# Non-root user for security
RUN useradd --create-home --shell /bin/bash arishem
USER arishem
WORKDIR /home/arishem/app

# Copy application code
COPY --chown=arishem:arishem . .

# Collect static files (needs SECRET_KEY set — use a dummy for build time)
RUN SECRET_KEY=build-time-dummy \
    DEBUG=False \
    DB_NAME=x DB_USER=x DB_PASSWORD=x DB_HOST=x DB_PORT=3306 \
    QDRANT_URL=http://localhost:6333 QDRANT_API_KEY=x \
    AWS_REGION=us-east-1 S3_BUCKET=x TRANSCRIBE_OUTPUT_BUCKET=x \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Gunicorn: 2 workers per CPU core is a good starting point.
# Adjust WEB_CONCURRENCY via env var in docker-compose / ECS task definition.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "backend.wsgi:application"]
