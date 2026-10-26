# syntax=docker/dockerfile:1
# ── Stage 1: build wheels/venv ────────────────────────────────────────────────
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /build
COPY requirements.txt .
# CPU-only torch keeps the image ~2 GB smaller than the default CUDA wheel.
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/home/arishem/.cache/huggingface
COPY --from=builder /opt/venv /opt/venv
RUN useradd --create-home --shell /usr/sbin/nologin arishem
USER arishem
WORKDIR /home/arishem/app
# Bake the embedding model in before copying the source: it depends only on the
# installed packages, so this layer stays cached when application code changes.
# Copying first would re-download the model on every rebuild.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# The model is now in the image, so stop the libraries asking the Hugging Face Hub
# whether a newer revision exists. That check cost ~5.7 s on every model load
# (1.1 s offline against 6.8 s online), and it fails outright without internet.
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

COPY --chown=arishem:arishem . .
RUN mkdir -p local_storage

# collectstatic needs settings to import; these values are build-time placeholders only.
RUN SECRET_KEY=build-time-placeholder DEBUG=False python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "backend.wsgi:application", "--config", "gunicorn.conf.py", \
     "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", \
     "--access-logfile", "-", "--error-logfile", "-"]
