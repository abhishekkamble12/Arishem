# Arishem Backend

A production-oriented, validated end-to-end **Retrieval-Augmented Generation (RAG) API** built with Django REST Framework. Upload documents and media files from AWS S3, embed them into a Qdrant vector store using Amazon Bedrock, and query them with natural language — all behind a JWT-secured, role-based API.

* **Hybrid AI Engine**: Initially built using **AWS Bedrock (Claude 3.5 Sonnet)**, the query inference engine was migrated to **Groq (Meta Llama 3.3 70B)** to reduce token latency to sub-second speeds and significantly cut inference costs. Vector embeddings remain generated via AWS Bedrock Titan.
* **Asynchronous Ingestion**: Media transcribing (AWS Transcribe) and document extractions are offloaded to **Celery** background tasks to prevent thread starvation and timeouts.

---

## Table of Contents

- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Local Setup](#local-setup)
  - [Without Docker](#without-docker)
  - [With Docker Compose](#with-docker-compose)
- [Running Tests](#running-tests)
- [API Reference](#api-reference)
  - [Authentication & Workspaces](#authentication--workspaces)
  - [AI / RAG Pipeline](#ai--rag-pipeline)
  - [AI Observability & Monitoring](#ai-observability--monitoring)
- [Ingestion Pipeline](#ingestion-pipeline)
- [Role-Based Access Control](#role-based-access-control)
- [Services Layer](#services-layer)
- [Data Models](#data-models)
- [Middleware](#middleware)
- [Docker](#docker)
- [CI/CD](#cicd)
- [Security Notes](#security-notes)
- [Supported File Types](#supported-file-types)
- [Configuration Reference](#configuration-reference)

---

## Architecture

```
Client (Auth / Select Workspace)
  │
  ▼
Django REST API (JWT auth + Active Workspace context + RBAC)
  │
  ├── POST /app/ai/upload ──► Enqueue Task ──► Return 202 Accepted (Immediately)
  │                                                │
  │                                                ▼
  │                                        [Celery Ingestion Task]
  │                                        ├─ Download from S3 / AWS Transcribe
  │                                        ├─ LangChain Splitting (800 token chunks)
  │                                        ├─ Bedrock Titan Embeddings (1024-dim)
  │                                        ├─ Qdrant Cloud (workspace metadata payload)
  │                                        └─ workspace_id payload index (Strict Filtered)
  │
  ├── POST /app/ai/query ──► Qdrant Similarity Search (Filtered by workspace_id)
  │                                │
  │                                ├── [Average score < 0.35] ──► Immediate OOD Rejection (No LLM call)
  │                                │
  │                                └── [Average score >= 0.35] ──► Groq Meta Llama 3.3 70B
  │                                                                     │
  │                                                                     ▼
  │                                                            Answer + Citations
  │
  └── Telemetry ──────────► PredictionLog / DriftLog (Observability & alerts)
```

Files are stored in **AWS S3**. The Celery background worker downloads them to a temp file for parsing, then deletes the temp file immediately after — nothing persists locally.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Django 5.1 + Django REST Framework 3.15 |
| Auth | JWT via `djangorestframework-simplejwt` 5.3 |
| Database | AWS RDS MySQL (SQLite for CI/testing) |
| Task Queue | Celery + RabbitMQ / Redis Broker |
| Vector store | Qdrant Cloud |
| Embeddings | Amazon Bedrock — Titan Embed Text v2 (1024-dim) |
| LLM | Groq — Meta Llama 3.3 70B (Migrated from Bedrock Claude 3.5 Sonnet to save cost) |
| File storage | AWS S3 |
| Video/audio transcription | AWS Transcribe |
| Document parsing | PyMuPDF (PDF), Docx2txt (DOCX), Unstructured (PPTX) |
| LangChain | `langchain-groq`, `langchain-aws`, `langchain-community`, `langchain-qdrant` |
| Server | Gunicorn |
| Containerisation | Docker (multi-stage) + Docker Compose |
| CI | GitHub Actions |
| Python | 3.12 |

---

## Project Structure

```
backend/
├── app/                            # Django application
│   ├── models.py                   # User (custom) + IngestedFile models
│   ├── views.py                    # All API endpoint handlers
│   ├── urls.py                     # App-level URL routing
│   ├── serializers.py              # RegisterSerializer, UserSerializer
│   ├── permissions.py              # IsAdmin, IsAdminOrEditor, IsAnyRole
│   ├── middleware.py               # Request/response logging middleware
│   ├── migrations/
│   │   └── 0001_initial.py         # DB schema migration
│   └── tests.py                    # Auth + permission test suite (11 tests)
│
├── backend/                        # Django project config
│   ├── settings.py                 # All settings (env-driven)
│   ├── test_settings.py            # Test overrides — forces SQLite in-memory
│   ├── urls.py                     # Root URL config
│   ├── wsgi.py / asgi.py           # WSGI / ASGI entry points
│   ├── .env                        # Local secrets (never commit)
│   └── .env.example                # Template for .env
│
├── Services/                       # Business logic / AI pipeline
│   ├── agent.py                    # RAG query agent (retrieval + LLM)
│   ├── Extractor.py                # Orchestrates ingestion pipeline
│   └── Ai_service/
│       ├── embedding.py            # Bedrock embeddings + Qdrant storage
│       ├── load_data.py            # S3 downloader (PDF, DOCX, PPTX)
│       ├── video_transcibing.py    # AWS Transcribe integration
│       └── __init__.py             # Public re-exports
│
├── setup_db.py                     # One-time production DB migration helper
├── manage.py
├── requirements.txt
└── Dockerfile
```

---

## Features

- **Asynchronous Ingestion Pipeline** — Offloads document parsing and audio/video transcription to **Celery** background tasks. Returns `202 Accepted` immediately, allowing users to track ingestion progress via UI status indicators.
- **Out-of-Domain (OOD) Confidence Rejection** — Bypasses the LLM and instantly returns a standard refusal if context similarity drops below `0.35` to prevent hallucinations.
- **Cost-Efficient Groq Inference** — Utilizes **Meta Llama 3.3 70B** on Groq for ultra-fast, cheap, and robust query generation (migrated from AWS Bedrock Claude 3.5 Sonnet).
- **Multi-Tenant Workspace Isolation** — SaaS-style organization folder architecture. Users are members of workspaces, and all uploaded files and RAG queries are isolated to the active workspace using Qdrant payload filters.
- **AI Observability & Monitoring** — Tracks every RAG prediction (inputs, outputs, latency, confidence, errors) and logs them in a structured schema.
- **Drift Detection & Alerts** — Automatically computes a sliding average of similarity scores to detect data drift, sending email alerts to administrators when drift or error thresholds are violated.
- **Interactive Dashboard** — Visualizes metrics such as queries per day, average response time, error rate, and drift history in a clean dashboard UI.
- **JWT authentication** — register, login, token refresh, workspaces listing, and profile endpoint
- **Refresh token blacklisting** — rotated refresh tokens are immediately invalidated
- **Role-based access control** — three roles: `admin`, `editor`, `viewer`
- **Multi-format ingestion** — PDF, DOCX, PPTX, MP4, MOV, AVI, MKV, MP3, WAV, FLAC, OGG, M4A
- **Video/audio transcription** — AWS Transcribe with speaker diarisation (up to 10 speakers)
- **Semantic chunking** — 800-token chunks with 150-token overlap
- **Vector embeddings** — Amazon Bedrock Titan Embeddings v2 (1024 dimensions, cosine similarity) with a Qdrant payload index for strict workspace filtering
- **Duplicate detection** — prevents re-ingesting the same S3 key
- **Audit trail** — every ingested file tracked with workspace, uploader, timestamp, and chunk count
- **Request logging** — every request logged with method, path, status, and duration
- **No trailing-slash redirects** — `APPEND_SLASH = False` prevents POST body loss on redirect
- **Docker-ready** — multi-stage build, non-root user, Gunicorn
- **CI pipeline** — GitHub Actions with SQLite in-memory, zero external dependencies

---

## Prerequisites

- Python 3.12+
- AWS account with access to:
  - **S3** — file storage
  - **Bedrock** — Titan Embeddings (enable Titan Text Embeddings access in AWS console)
  - **Transcribe** — for video/audio files
- **Groq API Key** — for Llama 3.3 inference
- **RabbitMQ** or **Redis** broker — for Celery background tasks
- **Qdrant Cloud** cluster (free tier works for development)
- **MySQL** database (AWS RDS for production; SQLite works locally with `DB_ENGINE` override)
- Docker + Docker Compose (optional)

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp backend/backend/.env.example backend/backend/.env
```

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Django secret key. Generate: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DEBUG` | ✅ | `True` for local dev, `False` in production |
| `ALLOWED_HOSTS` | ✅ | Comma-separated, e.g. `localhost,127.0.0.1` |
| `DB_HOST` | ✅ | MySQL host (RDS endpoint or `localhost`) |
| `DB_PORT` | ✅ | MySQL port, default `3306` |
| `DB_NAME` | ✅ | Database name |
| `DB_USER` | ✅ | Database user |
| `DB_PASSWORD` | ✅ | Database password |
| `DB_ENGINE` | ❌ | Set to `django.db.backends.sqlite3` for local/CI |
| `QDRANT_URL` | ✅ | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | ✅ | Qdrant Cloud API key |
| `QDRANT_COLLECTION` | ❌ | Collection name, default `documents` |
| `AWS_ACCESS_KEY_ID` | ❌ | Leave blank in production — use IAM role instead |
| `AWS_SECRET_ACCESS_KEY` | ❌ | Leave blank in production — use IAM role instead |
| `AWS_REGION` | ✅ | AWS region, e.g. `us-east-1` |
| `S3_BUCKET` | ✅ | S3 bucket where files are stored |
| `TRANSCRIBE_OUTPUT_BUCKET` | ✅ | S3 bucket for Transcribe JSON output (can be same as `S3_BUCKET`) |
| `GROQ_API_KEY` | ✅ | Groq API Key for inference |
| `GROQ_MODEL_ID` | ❌ | Model ID on Groq, default `llama-3.3-70b-versatile` |
| `RAG_CONFIDENCE_THRESHOLD` | ❌ | OOD Rejection Threshold, default `0.35` |
| `RAG_TOP_K` | ❌ | Chunks to retrieve per query, default `5` |

> **Production tip:** Never set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in production. Attach an IAM role to your EC2 instance or ECS task — boto3 picks it up automatically.

---

## Local Setup

### Without Docker

**1. Clone and navigate**

```bash
git clone <repo-url>
cd Arishem/backend
```

**2. Create a virtual environment**

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

> On Linux/macOS you may need `default-libmysqlclient-dev` and `pkg-config` installed via your system package manager before `mysqlclient` will compile.

**4. Configure environment**

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your credentials
```

For a quick local run without MySQL, add these two lines to `.env`:

```
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=db.sqlite3
```

**5. Apply migrations**

If this is a **fresh** database (SQLite or empty MySQL):

```bash
python manage.py migrate
```

If your MySQL already has Django's system tables from a previous project (e.g. `auth_user` exists), run the one-time helper instead:

```bash
python setup_db.py        # fixes schema, creates app_user + app_ingestedfile
python manage.py migrate  # applies any remaining migrations
```

**6. Create a superuser (optional)**

```bash
python manage.py createsuperuser
```

**7. Start the Celery worker**

In a separate terminal, start the Celery background worker:
```bash
celery -A backend worker --loglevel=info -P solo
```

**8. Start the development server**

```bash
python manage.py runserver
```

API available at `http://localhost:8000`.

---

### With Docker Compose

**1. Configure environment**

```bash
cp backend/backend/.env.example backend/backend/.env
# Edit backend/backend/.env with your credentials
```

**2. Build and start**

```bash
docker compose up --build
```

Two containers start:
- `migrate` — runs `python manage.py migrate` then exits
- `api` — Gunicorn on port `8000`, starts only after migrations succeed

**3. Access the API**

```
http://localhost:8000
```

**Stop the stack**

```bash
docker compose down
```

---

## Running Tests

Tests use **SQLite in-memory** — no MySQL, Qdrant, or AWS credentials needed.

```bash
cd backend
python manage.py test --verbosity=2 --settings=backend.test_settings
```

The test suite covers:
- Register with default viewer role
- Register with explicit role
- Login returns JWT tokens
- Login rejects wrong password
- `GET /auth/me` requires authentication
- `GET /auth/me` returns correct user and role
- Viewer blocked from upload (403)
- Editor allowed through to upload (hits S3 — expected 502 in tests, not 403)
- Viewer can query (hits Qdrant — expected 502 in tests, not 403)
- Viewer can list files (200)
- Unauthenticated requests get 401 on all protected routes

---

# Arishem — End-to-End Test Results

## Test Setup
- Date: 2026-08-05
- Environment: Local Docker, SQLite fallback, Qdrant Cloud free tier, Groq API (Llama 3.3 70B)
- Test corpus: SOP-104_Data_Retention_Policy.pdf
- Confidence threshold: 0.35
- Top-K: 5

## Test Results

| Operation | Latency | Status | Confidence | Insight |
|---|---|---|---|---|
| Ingestion (1 PDF) | 2,222ms | ✅ Success | N/A | PDF chunked and stored in Qdrant |
| Query Q1 (in-domain) | 1,949ms | ✅ Success | 0.7258 | Correctly answered "90 days", cited SOP-104 |
| Query Q2 (in-domain) | 914ms | ✅ Success | 0.3707 | Correctly answered compliance officer email, cited SOP-104 |
| Query Q3 (OOD) | 625ms | ✅ Success (rejection) | 0.0986 | Bypassed LLM call due to confidence < 0.35 |

## Key Findings

1. **OOD rejection works as designed.** Out-of-domain query confidence (0.0986) was well below threshold (0.35), system correctly skipped LLM generation.
2. **Citation grounding holds.** Both in-domain queries returned source citations (SOP-104_Data_Retention_Policy.pdf).
3. **Latency range observed:** 625ms–1,949ms. Median ~1.4s. Cold-start cost amortized after first query.
4. **Cost estimate:** Based on Groq pricing (~$0.30/1M tokens) and ~1K tokens per query, ~$0.0003/query for inference.

## Files
- `reports/test_run.txt` — raw query output
- `reports/benchmark.md` — this file
- `pcaps/SOP-104_Data_Retention_Policy.pdf` — input documents

---

## API Reference

All endpoints are prefixed with `/app/`. No trailing slashes. Base URL in local development: `http://localhost:8000`.

### Authentication

#### `POST /app/auth/register`

Create a new user account. Returns JWT tokens immediately.

**Access:** Public

**Request body:**

```json
{
  "email": "user@example.com",
  "username": "johndoe",
  "password": "SecurePass123!",
  "password2": "SecurePass123!",
  "role": "viewer"
}
```

`role` is optional, defaults to `viewer`. Valid values: `viewer`, `editor`, `admin`.  
`username` is optional, defaults to the part of the email before `@`.

**Response `201`:**

```json
{
  "message": "Account created successfully",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "johndoe",
    "role": "viewer",
    "date_joined": "2024-01-15T10:30:00Z",
    "is_active": true
  },
  "tokens": {
    "access": "<jwt-access-token>",
    "refresh": "<jwt-refresh-token>"
  }
}
```

---

#### `POST /app/auth/login`

Authenticate and receive JWT tokens.

**Access:** Public

**Request body:**

```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response `200`:**

```json
{
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "johndoe",
    "role": "viewer",
    "date_joined": "2024-01-15T10:30:00Z",
    "is_active": true
  },
  "tokens": {
    "access": "<jwt-access-token>",
    "refresh": "<jwt-refresh-token>"
  }
}
```

---

#### `POST /app/auth/token/refresh`

Exchange a refresh token for a new access + refresh token pair.  
The old refresh token is **immediately blacklisted** after use.

**Access:** Public

**Request body:**

```json
{
  "refresh": "<jwt-refresh-token>"
}
```

**Response `200`:**

```json
{
  "access": "<new-jwt-access-token>",
  "refresh": "<new-jwt-refresh-token>"
}
```

---

#### `GET /app/auth/me`

Get the current authenticated user's profile.

**Access:** Any authenticated user

**Headers:** `Authorization: Bearer <access-token>`

**Response `200`:**

```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "johndoe",
  "role": "viewer",
  "date_joined": "2024-01-15T10:30:00Z",
  "is_active": true
}
```

---

#### `GET /app/auth/workspaces`

Get the list of workspaces that the authenticated user belongs to.

**Access:** Any authenticated user

**Headers:** `Authorization: Bearer <access-token>`

**Response `200`:**

```json
[
  {
    "id": 1,
    "name": "Default Workspace",
    "created_at": "2026-06-17T15:00:00Z"
  }
]
```

---

### AI / RAG Pipeline

All AI endpoints require a valid JWT:

```
Authorization: Bearer <access-token>
```

---

#### `POST /app/ai/upload`

Ingest a file from S3 into the Qdrant vector store. The file must already exist in your configured S3 bucket.

**Access:** `editor` or `admin` role only

**Request body:**

```json
{
  "s3_key": "documents/report.pdf",
  "workspace_id": 1
}
```

`workspace_id` is optional, defaulting to the user's first available workspace.

**Response `201`:**

```json
{
  "message": "File ingested successfully",
  "s3_key": "documents/report.pdf",
  "file_type": "pdf",
  "chunks_stored": 42,
  "uploaded_by": "user@example.com"
}
```

---

#### `POST /app/ai/upload-direct`

Upload a file directly from the browser/client. The API saves the file to S3 under `uploads/` and then runs the ingestion pipeline.

**Access:** `editor` or `admin` role only

**Request type:** `multipart/form-data`

**Request body:**
- `file`: The binary file to upload.
- `workspace_id`: (Optional) The workspace ID.

**Response `201`:**

```json
{
  "message": "File ingested successfully",
  "s3_key": "uploads/report.pdf",
  "file_type": "pdf",
  "chunks_stored": 42,
  "uploaded_by": "user@example.com"
}
```

---

#### `POST /app/ai/query`

Ask a natural language question over all ingested documents in a specific workspace.

**Access:** Any authenticated user (`viewer`, `editor`, `admin`)

**Request body:**

```json
{
  "question": "What are the key findings in the Q1 report?",
  "top_k": 5,
  "workspace_id": 1
}
```

`workspace_id` is optional, defaulting to the user's first available workspace. `top_k` is optional, defaults to the `RAG_TOP_K` env var (default `5`).

**Response `200`:**

```json
{
  "answer": "According to the Q1 report [documents/report.pdf], the key findings are...",
  "sources": ["documents/report.pdf", "documents/summary.docx"],
  "chunks": 5
}
```

---

#### `GET /app/ai/files`

List all files ingested into the vector store for a specific workspace.

**Access:** Any authenticated user

**Query parameters:**
- `workspace_id`: (Optional) Workspace ID. Defaults to user's first workspace.

**Response `200`:**

```json
{
  "files": [
    {
      "s3_key": "documents/report.pdf",
      "file_type": "pdf",
      "chunks_stored": 42,
      "ingested_at": "2024-01-15T10:30:00Z",
      "uploaded_by__email": "editor@example.com"
    }
  ],
  "total": 1
}
```

---

#### `DELETE /app/ai/files/delete`

Delete an ingested file tracking record. Note that this only removes the file metadata record from the relational database; it does not delete S3 files or the Qdrant vectors.

**Access:** `editor` or `admin` role only

**Request body:**
```json
{
  "s3_key": "documents/report.pdf"
}
```

**Response `200`:**
```json
{
  "message": "'documents/report.pdf' removed successfully"
}
```

---

### AI Observability & Monitoring

All monitoring endpoints require a valid JWT with `editor` or `admin` roles.

---

#### `GET /app/ai/monitoring`

Fetch aggregated analytics and logs for the Observability Dashboard.

**Access:** `editor` or `admin` role only

**Query parameters:**
- `workspace_id`: (Optional) Workspace ID. Defaults to user's first workspace.

**Response `200`:**
```json
{
  "total_predictions": 152,
  "error_count": 3,
  "avg_latency": 2450.35,
  "avg_confidence": 0.5234,
  "chart_data": [
    { "date": "2026-06-11", "count": 12 },
    { "date": "2026-06-12", "count": 25 },
    { "date": "2026-06-13", "count": 18 },
    { "date": "2026-06-14", "count": 30 },
    { "date": "2026-06-15", "count": 22 },
    { "date": "2026-06-16", "count": 15 },
    { "date": "2026-06-17", "count": 30 }
  ],
  "recent_drifts": [
    {
      "id": 1,
      "drift_score": 0.3124,
      "timestamp": "2026-06-17T15:20:00Z"
    }
  ]
}
```

---

## Ingestion Pipeline

### Document Flow (PDF / DOCX / PPTX)

```
POST /app/ai/upload  { "s3_key": "report.pdf" }
        │
        ▼
  Extractor.extract_and_chunk()
        │
        ├── download_from_s3()  →  temp file (/tmp/tmpXXXX.pdf)
        │
        ├── LangChain loader
        │     .pdf  → PyMuPDFLoader         (page-aware)
        │     .docx → Docx2txtLoader
        │     .pptx → UnstructuredPowerPointLoader
        │
        ├── RecursiveCharacterTextSplitter
        │     chunk_size=800, chunk_overlap=150
        │
        └── List[Document]  (metadata: source, bucket, page)
                │
                ▼
        embed_and_store()
                │
                ├── BedrockEmbeddings (Titan Embed Text v2, 1024-dim)
                │
                └── QdrantVectorStore.from_documents()
                        │
                        ▼
                  Qdrant Cloud collection
```

### Media / Video Flow (MP4, MP3, etc.)

```
POST /app/ai/upload  { "s3_key": "lecture.mp4" }
        │
        ▼
  Extractor.extract_and_chunk()
        │
        ▼
  transcribe_media()
        │
        ├── start_transcription_job()     (AWS Transcribe)
        │     - language: en-US
        │     - speaker diarisation (up to 10 speakers)
        │     - output to TRANSCRIBE_OUTPUT_BUCKET
        │
        ├── poll every 5s, timeout 30 min
        │
        ├── fetch transcript JSON from S3
        │     (handles all S3 URI formats — path-style + virtual-hosted)
        │
        └── Document(page_content=transcript_text,
                     metadata={source, bucket, job_name, media_type})
                │
                ▼
  RecursiveCharacterTextSplitter  →  List[Document]
                │
                ▼
        embed_and_store()  →  Qdrant Cloud
```

> **Eventual Consistency & Dual-Write Resolution:**
> Ingestion operations involve writing metadata to a relational database (MySQL) and vectors to a vector database (Qdrant) — two non-transactional distributed data stores. To prevent partial failure inconsistencies:
> 1. Django writes the file record in a `PENDING` state first.
> 2. The worker picks up the job and transitions it to `PROCESSING` before generating embeddings.
> 3. The record is updated to `SUCCESS` (setting the chunk count) **only after** Qdrant confirms successful storage of the vectors.
> 4. Any failure during transcription, extraction, or vector storage transitions the record to `FAILED`, storing the raw error message.
> 5. A periodic reconciliation Celery task runs to identify and mark `FAILED` any records stuck in a transition state (`PENDING` or `PROCESSING`) for longer than 30 minutes.
>
> **Asynchronous Producer-Consumer Ingestion Queue & Backpressure Handling:**
> Synchronous execution of text extraction and 30-minute media transcription jobs blocks web request workers, leading to thread starvation, DB connection exhaustion, and gateway timeouts.
> To address this, the pipeline has been decoupled into a producer-consumer architecture utilizing **Celery + RabbitMQ/Redis**.
> - **Producer (Django API)**: Writes a file tracking record in the relational DB as `PENDING` and immediately enqueues the job to RabbitMQ. Returns `202 Accepted` with a job ID in under 100ms.
> - **Consumer (Celery Workers)**: Asynchronously consumes tasks, polling AWS Transcribe, executing chunking, calling Bedrock embeddings, and saving to Qdrant.
> - **Backpressure Handling**: If workers fall behind and jobs start backing up, the system must protect database and worker resources. The API enforces a strict queue depth threshold (`MAX_INGESTION_QUEUE_DEPTH`, default 50) checking active jobs (`PENDING` or `PROCESSING`). If this limit is breached, the API immediately rejects new ingestion requests with `503 Service Unavailable`, forcing client-side backoff.
> - **Scale Mitigation**: Under high production loads, workers should be autoscaled horizontally (e.g., KEDA on Kubernetes scaling workers based on RabbitMQ queue length). Rejecting with a `503` acts as a fail-safe threshold to protect downstream services when autoscaling cannot keep up.
>
> **Metered Dependency Cost-Control & Role-Based Throttling:**
> Unlike standard web APIs that read from local databases, AI-engineering APIs invoke metered external services (AWS Bedrock, AWS Transcribe, Qdrant Cloud, and Groq LLMs) where each invocation translates to real financial costs. 
> To enforce cost control and budgeting:
> - **Dynamic Role Throttling**: A custom DRF throttle class `CostControlRoleThrottle` dynamically limits API calls based on workspace roles, ensuring expensive operations are not abused:
>   - `admin`: High allowance (e.g., 100 req/min) for workspace management.
>   - `editor`: Medium allowance (e.g., 60 req/min) to balance ingestion tasks.
>   - `viewer`: Heavily capped allowance (e.g., 10 req/min) to prevent query token burn.
> - **Rejection Bypassing**: The system incorporates Out-of-Domain (OOD) Confidence Rejection. If retrieved chunk similarity averages below `0.35`, the LLM inference call is skipped, returning a cached refusal response to control external LLM token costs.
>
> **Multi-Tenant Data Isolation Architecture (Tradeoffs):**
> When building multi-tenant RAG applications, two major patterns are used for database level isolation:
> 1. **Collection-per-Tenant**: Provisioning a separate Qdrant collection for each workspace.
>    * *Pros*: Strongest security isolation boundaries, zero risk of cross-tenant leakage, easier collection deletion.
>    * *Cons*: Excessive operational overhead, doesn't scale to thousands of tenants due to hardware/RAM overhead per collection.
> 2. **Metadata Payload Filtering (Used Here)**: Storing all data in a single collection and filtering search requests using tenant metadata.
>    * *Pros*: Highly cost-efficient, operates on a single shared index, scales automatically.
>    * *Cons*: Requires strict validation rules to avoid leaks due to coding bugs.
> 
> *Our Implementation*: To address data leakage, Arishem enforces strict workspace filtering at the API layer and the vector database layer via Qdrant's payload index on `metadata.workspace_id`. Furthermore, the system layers role-based context constraints: users with the `viewer` role are dynamically locked to their own uploads via a secondary `metadata.uploaded_by` search filter. Admin and editor roles query across all workspace resources.

---

## Role-Based Access Control

Roles are stored via Django's built-in `Group` model. Each user belongs to exactly one group.

| Endpoint | viewer | editor | admin |
|---|---|---|---|
| `POST /auth/register` | ✅ | ✅ | ✅ |
| `POST /auth/login` | ✅ | ✅ | ✅ |
| `GET /auth/me` | ✅ | ✅ | ✅ |
| `POST /ai/upload` | ❌ | ✅ | ✅ |
| `POST /ai/query` | ✅ | ✅ | ✅ |
| `GET /ai/files` | ✅ | ✅ | ✅ |
| Django admin panel | ❌ | ❌ | ✅ |

**Permission classes (`app/permissions.py`):**

| Class | Grants access to |
|---|---|
| `IsAnyRole` | Any authenticated user (viewer, editor, admin) |
| `IsAdminOrEditor` | editor and admin only |
| `IsAdmin` | admin only |

---

## Services Layer

### `Services/Extractor.py`

Ingestion orchestrator. Routes files to the correct loader and returns `List[Document]` ready for embedding.

```python
from Services.Extractor import extract_and_chunk

chunks = extract_and_chunk(bucket_name="my-bucket", s3_key="docs/report.pdf")
# Returns List[Document]
```

Each `Document` carries:
- `source` — original S3 key
- `bucket` — S3 bucket name
- `page` — page/slide number (documents only)
- `job_name` — Transcribe job name (media only)
- `media_type` — file extension without dot (media only)

---

### `Services/Ai_service/embedding.py`

Bedrock embeddings + Qdrant storage. Uses lazy singletons for both clients.

```python
from Services.Ai_service.embedding import embed_and_store, get_vector_store

# Store chunks
stored_count = embed_and_store(chunks)

# Retrieve for search
vector_store = get_vector_store()
results = vector_store.similarity_search("my question", k=5)
```

The Qdrant collection is created automatically on first use.

---

### `Services/Ai_service/video_transcibing.py`

AWS Transcribe integration. Returns a single `Document` with the full transcript.

```python
from Services.Ai_service.video_transcibing import transcribe_media

doc = transcribe_media(bucket_name="my-bucket", s3_key="videos/lecture.mp4")
# Returns Document with transcript as page_content
```

Correctly handles all AWS S3 URI formats (path-style, virtual-hosted, regional).

---

### `Services/agent.py`

RAG query agent. Retrieves chunks from Qdrant and calls Claude for a grounded answer.

```python
from Services.agent import query

result = query("What is the main topic of the uploaded documents?", top_k=5)
# {
#   "answer": "...",
#   "sources": ["docs/report.pdf"],
#   "chunks": 5
# }
```

Claude is instructed via system prompt to only use retrieved context and always cite sources. Temperature is set to `0.2` for factual, grounded responses.

---

## Data Models

### `Workspace` (`app_workspace` table)

Groups users and files to provide SaaS-style tenant folder isolation.

| Field | Type | Notes |
|---|---|---|
| `id` | AutoField (INT) | Primary key |
| `name` | CharField(100) | Name of the workspace / folder |
| `created_at` | DateTimeField | Creation timestamp |
| `members` | M2M → User | Users who belong to this workspace |

---

### `User` (`app_user` table)

Extends Django's `AbstractUser`. Uses **email as the login identifier**.

| Field | Type | Notes |
|---|---|---|
| `id` | AutoField (INT) | Primary key |
| `email` | EmailField | Unique, used for login |
| `username` | CharField | Kept for admin compatibility, auto-generated if omitted |
| `groups` | M2M → Group | Role is derived from the first group |
| `is_active` | BooleanField | Disabled accounts cannot log in |

**Properties:**
- `user.role` — returns `"admin"`, `"editor"`, or `"viewer"` (defaults to `"viewer"` if no group)
- `user.has_role("admin", "editor")` — returns `True` if the user has any of the listed roles

> **DB note:** The table is named `app_user` (not `auth_user`) to avoid conflicts with Django's default user table on existing databases.

---

### `IngestedFile` (`app_ingestedfile` table)

Tracks every file successfully ingested into Qdrant.

| Field | Type | Notes |
|---|---|---|
| `id` | AutoField (INT) | Primary key |
| `s3_bucket` | CharField(255) | S3 bucket name |
| `s3_key` | CharField(500) | S3 object key |
| `file_type` | CharField(10) | One of the `FileType` choices |
| `chunks_stored` | PositiveIntegerField | Number of vector chunks created |
| `ingested_at` | DateTimeField | Auto-set on creation |
| `transcribe_job` | CharField(255) | AWS Transcribe job name (media only, nullable) |
| `uploaded_by` | FK → User | `SET NULL` on user deletion |
| `workspace` | FK → Workspace | Links files to the workspace container |

Unique constraint on `(s3_bucket, s3_key)` — prevents duplicate ingestion.

---

### `PredictionLog` (`app_predictionlog` table)

Logs every prediction and RAG query made for observability and drift tracking.

| Field | Type | Notes |
|---|---|---|
| `id` | AutoField (INT) | Primary key |
| `workspace` | FK → Workspace | The workspace this prediction was run in |
| `user` | FK → User | The user who triggered the request |
| `input_text` | TextField | Natural language prompt / query |
| `prediction_text` | TextField | Grounded LLM response |
| `response_time_ms` | PositiveIntegerField | Response latency in milliseconds |
| `confidence` | FloatField | Score proxy (e.g. average cosine similarity score) |
| `error_msg` | TextField | Error details if the query failed |
| `timestamp` | DateTimeField | Log timestamp |

---

### `DriftLog` (`app_driftlog` table)

Records data drift events detected in the system.

| Field | Type | Notes |
|---|---|---|
| `id` | AutoField (INT) | Primary key |
| `workspace` | FK → Workspace | The workspace experiencing drift |
| `drift_score` | FloatField | Average confidence score of the current sliding window |
| `is_drift_detected`| BooleanField | Flags whether drift was detected |
| `reference_count` | IntegerField | Size of the baseline comparison log set |
| `current_count` | IntegerField | Size of the active sliding window evaluated |
| `timestamp` | DateTimeField | Drift detection event timestamp |

---

## Middleware

`app.middleware.RequestLoggingMiddleware` logs every request:

```
INFO 2024-01-15 10:30:00 middleware POST /app/ai/upload → 201  (245.3ms)
```

Logs go to stdout. Logger name is `arishem.requests`.

---

## Docker

Multi-stage `Dockerfile`:

1. **Builder stage** — compiles C extensions (`mysqlclient`, `libpoppler`) into `/install/packages`
2. **Runtime stage** — copies only compiled packages, no build tools, smaller final image

Security hardening:
- Runs as non-root user `arishem`
- No compilers in the final image
- Static files collected at build time with dummy env vars

**Gunicorn settings:**

| Setting | Value | Override |
|---|---|---|
| Workers | 2 | `WEB_CONCURRENCY` env var |
| Timeout | 120s | Dockerfile `CMD` |
| Bind | `0.0.0.0:8000` | Dockerfile `CMD` |

---

## CI/CD

GitHub Actions at `.github/workflows/django.yml` runs on every push and PR to `main`.

**Pipeline steps:**

1. Checkout code
2. Write `.env` file (from `ENV_FILE` secret if set, otherwise CI defaults)
3. Set up Python 3.12 with pip cache
4. Install system dependencies (`libmysqlclient-dev`, `gcc`)
5. Install Python dependencies
6. `python manage.py check --deploy` (non-fatal) + `python manage.py check`
7. `python manage.py migrate --settings=backend.test_settings` (SQLite in-memory)
8. `python manage.py test --verbosity=2 --settings=backend.test_settings`

Tests always use **SQLite in-memory** via `backend/test_settings.py` — no MySQL, Qdrant, or AWS credentials needed.

To run integration tests against real services, create an `ENV_FILE` repository secret with the full contents of your `.env`.

---

## Security Notes

- **Never commit `.env`** — it is in `.gitignore`
- **Use IAM roles in production** — do not set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` on EC2/ECS
- **`DEBUG=False` in production** — the `check --deploy` CI step will warn you
- **`SECRET_KEY`** — generate a fresh one per environment, never reuse the example value
- **Passwords** — validated against Django's full validator suite (similarity, length, common passwords, numeric-only)
- **JWT access tokens** expire in 1 hour; refresh tokens rotate on every use and old tokens are immediately blacklisted
- **`APPEND_SLASH = False`** — prevents POST body loss caused by 301 redirects on clients that don't follow redirects with body
- **`setup_db.py`** — the one-time DB migration helper. It is idempotent and safe to re-run, but contains no secrets itself

---

## Supported File Types

### Documents
| Extension | Parser |
|---|---|
| `.pdf` | PyMuPDF — fast, page-aware extraction |
| `.docx` | Docx2txt — full text including tables |
| `.pptx` | Unstructured — slide-aware extraction |

### Media (transcribed via AWS Transcribe)
| Extension | Type |
|---|---|
| `.mp4`, `.mov`, `.avi`, `.mkv` | Video |
| `.mp3`, `.wav`, `.flac`, `.ogg`, `.m4a` | Audio |

---

## Configuration Reference

### JWT Token Lifetimes

| Token | Lifetime | Blacklisted on rotation |
|---|---|---|
| Access | 1 hour | N/A |
| Refresh | 7 days | Yes — old token invalid immediately |

### Chunking Parameters

| Parameter | Value | Location |
|---|---|---|
| `CHUNK_SIZE` | 800 tokens | `Services/Extractor.py` |
| `CHUNK_OVERLAP` | 150 tokens | `Services/Extractor.py` |

### Embedding Model

| Parameter | Value |
|---|---|
| Model | `amazon.titan-embed-text-v2:0` |
| Dimensions | 1024 |
| Distance metric | Cosine |

### LLM

| Parameter | Value | Override |
|---|---|---|
| Model | `anthropic.claude-3-5-sonnet-20241022-v2:0` | `BEDROCK_MODEL_ID` env var |
| Temperature | 0.2 | `Services/agent.py` |
| Max tokens | 2048 | `Services/agent.py` |
| Default top-k | 5 | `RAG_TOP_K` env var |

### Transcription

| Parameter | Value |
|---|---|
| Language | `en-US` |
| Speaker diarisation | Enabled |
| Max speakers | 10 |
| Poll interval | 5 seconds |
| Timeout | 30 minutes |
| Output bucket | `TRANSCRIBE_OUTPUT_BUCKET` env var |
| Output key prefix | `transcripts/<filename>/` |

### AI Observability & Drift Detection

| Parameter | Value | Description |
|---|---|---|
| Evaluation Window | 50 queries | Calculates sliding average confidence over the last 50 queries |
| Drift Threshold | 0.35 | Average similarity score below which drift is flagged |
| Alert Cooldown | 1 hour | Avoids spamming admins with drift emails |
