# Arishem Backend

A production-ready **Retrieval-Augmented Generation (RAG)** API built with Django REST Framework. Arishem lets you ingest documents and media files from AWS S3, embed them into a Qdrant vector store using Amazon Bedrock, and query them with natural language — all behind a JWT-secured, role-based API.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Local Development Setup](#local-development-setup)
  - [Without Docker](#without-docker)
  - [With Docker Compose](#with-docker-compose)
- [Running Tests](#running-tests)
- [API Reference](#api-reference)
  - [Authentication](#authentication)
  - [AI / RAG Pipeline](#ai--rag-pipeline)
- [Ingestion Pipeline](#ingestion-pipeline)
  - [Document Flow](#document-flow)
  - [Media / Video Flow](#media--video-flow)
- [Role-Based Access Control](#role-based-access-control)
- [Services Layer](#services-layer)
  - [Extractor](#extractor)
  - [Embedding](#embedding)
  - [Video Transcription](#video-transcription)
  - [RAG Agent](#rag-agent)
- [Data Models](#data-models)
- [Middleware](#middleware)
- [Docker](#docker)
- [CI/CD](#cicd)
- [Security Notes](#security-notes)
- [Supported File Types](#supported-file-types)
- [Configuration Reference](#configuration-reference)

---

## Architecture Overview

```
Client
  │
  ▼
Django REST API  (JWT auth + RBAC)
  │
  ├── POST /app/ai/upload ──► Extractor ──► S3 download / AWS Transcribe
  │                                │
  │                                ▼
  │                         LangChain Splitter
  │                                │
  │                                ▼
  │                    Bedrock Titan Embeddings
  │                                │
  │                                ▼
  │                         Qdrant Cloud (vector store)
  │
  └── POST /app/ai/query ──► Qdrant similarity search
                                   │
                                   ▼
                          Bedrock Claude (LLM)
                                   │
                                   ▼
                            Answer + Sources
```

All file storage lives in **AWS S3**. The API never stores files locally in production — it downloads them to a temp file for parsing, then cleans up immediately.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Django 5.1 + Django REST Framework 3.15 |
| Auth | JWT via `djangorestframework-simplejwt` |
| Database | AWS RDS MySQL (SQLite for CI/testing) |
| Vector store | Qdrant Cloud |
| Embeddings | Amazon Bedrock — Titan Embed Text v2 (1024-dim) |
| LLM | Amazon Bedrock — Claude 3.5 Sonnet |
| File storage | AWS S3 |
| Video transcription | AWS Transcribe |
| Document parsing | PyMuPDF (PDF), Docx2txt (DOCX), Unstructured (PPTX) |
| LangChain | `langchain-aws`, `langchain-community`, `langchain-qdrant` |
| Server | Gunicorn |
| Containerisation | Docker (multi-stage) + Docker Compose |
| CI | GitHub Actions |
| Python | 3.12 |

---

## Project Structure

```
backend/
├── app/                        # Django application
│   ├── models.py               # User (custom) + IngestedFile models
│   ├── views.py                # All API endpoint handlers
│   ├── urls.py                 # App-level URL routing
│   ├── serializers.py          # RegisterSerializer, UserSerializer
│   ├── permissions.py          # IsAdmin, IsAdminOrEditor, IsAnyRole
│   ├── middleware.py           # Request/response logging middleware
│   └── tests.py                # Test suite
│
├── backend/                    # Django project config
│   ├── settings.py             # All settings (env-driven)
│   ├── urls.py                 # Root URL config
│   ├── wsgi.py                 # WSGI entry point
│   ├── asgi.py                 # ASGI entry point
│   ├── .env                    # Local secrets (never commit)
│   └── .env.example            # Template for .env
│
├── Services/                   # Business logic / AI pipeline
│   ├── agent.py                # RAG query agent (retrieval + LLM)
│   ├── Extractor.py            # Orchestrates ingestion pipeline
│   └── Ai_service/
│       ├── embedding.py        # Bedrock embeddings + Qdrant storage
│       ├── load_data.py        # S3 downloader (PDF, DOCX, PPTX)
│       ├── video_transcibing.py # AWS Transcribe integration
│       └── __init__.py         # Public re-exports
│
├── manage.py
├── requirements.txt
└── Dockerfile
```

---

## Features

- **JWT authentication** — register, login, token refresh, and profile endpoint
- **Role-based access control** — three roles: `admin`, `editor`, `viewer`
- **Multi-format ingestion** — PDF, DOCX, PPTX, MP4, MOV, AVI, MKV, MP3, WAV, FLAC, OGG, M4A
- **Video/audio transcription** — AWS Transcribe with speaker diarisation (up to 10 speakers)
- **Semantic chunking** — 800-token chunks with 150-token overlap via `RecursiveCharacterTextSplitter`
- **Vector embeddings** — Amazon Bedrock Titan Embed Text v2 (1024 dimensions, cosine similarity)
- **RAG querying** — top-k retrieval from Qdrant + Claude 3.5 Sonnet grounded answers with source citations
- **Duplicate detection** — prevents re-ingesting the same S3 key
- **Audit trail** — every ingested file is tracked with uploader, timestamp, and chunk count
- **Request logging** — every request logged with method, path, status, and duration
- **Docker-ready** — multi-stage build, non-root user, Gunicorn
- **CI pipeline** — GitHub Actions with SQLite in-memory for fast, dependency-free tests

---

## Prerequisites

- Python 3.12+
- An **AWS account** with access to:
  - S3 (file storage)
  - Bedrock (Titan Embeddings + Claude) — model access must be enabled in the AWS console
  - Transcribe (for video/audio files)
- A **Qdrant Cloud** cluster (free tier works for development)
- A **MySQL** database (AWS RDS recommended for production; SQLite works for local dev)
- Docker + Docker Compose (optional, for containerised setup)

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp backend/backend/.env.example backend/backend/.env
```

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Django secret key. Generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DEBUG` | ✅ | `True` for local dev, `False` in production |
| `ALLOWED_HOSTS` | ✅ | Comma-separated list, e.g. `localhost,127.0.0.1` |
| `DB_HOST` | ✅ | MySQL host (RDS endpoint or `localhost`) |
| `DB_PORT` | ✅ | MySQL port, default `3306` |
| `DB_NAME` | ✅ | Database name |
| `DB_USER` | ✅ | Database user |
| `DB_PASSWORD` | ✅ | Database password |
| `DB_ENGINE` | ❌ | Override to `django.db.backends.sqlite3` for local/CI |
| `QDRANT_URL` | ✅ | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | ✅ | Qdrant Cloud API key |
| `QDRANT_COLLECTION` | ❌ | Collection name, default `documents` |
| `AWS_ACCESS_KEY_ID` | ❌ | Leave blank in production — use IAM role instead |
| `AWS_SECRET_ACCESS_KEY` | ❌ | Leave blank in production — use IAM role instead |
| `AWS_REGION` | ✅ | AWS region, e.g. `us-east-1` |
| `S3_BUCKET` | ✅ | S3 bucket where files are stored |
| `TRANSCRIBE_OUTPUT_BUCKET` | ✅ | S3 bucket for Transcribe JSON output (can be same as `S3_BUCKET`) |
| `BEDROCK_MODEL_ID` | ❌ | Claude model ID, default `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `RAG_TOP_K` | ❌ | Number of chunks to retrieve per query, default `5` |

> **Production tip:** Never set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in production. Attach an IAM role to your EC2 instance or ECS task instead — boto3 picks it up automatically.

---

## Local Development Setup

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

For a quick local run without MySQL, add these two lines to your `.env`:

```
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=db.sqlite3
```

**5. Run migrations**

```bash
python manage.py migrate
```

**6. Create a superuser (optional)**

```bash
python manage.py createsuperuser
```

**7. Start the development server**

```bash
python manage.py runserver
```

The API is now available at `http://localhost:8000`.

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

This starts two containers:
- `migrate` — runs `python manage.py migrate` then exits
- `api` — Gunicorn server on port `8000`, starts only after migrations succeed

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

The test suite uses SQLite in-memory so no external database is needed.

```bash
cd backend
python manage.py test --verbosity=2
```

For CI, the GitHub Actions workflow sets all required environment variables automatically — no secrets needed for the test run.

---

## API Reference

All endpoints are prefixed with `/app/`. The base URL in local development is `http://localhost:8000`.

### Authentication

#### `POST /app/auth/register`

Create a new user account. Returns JWT tokens immediately.

**Access:** Public (no token required)

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

`role` is optional and defaults to `viewer`. Valid values: `viewer`, `editor`, `admin`.

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

Exchange a refresh token for a new access token.

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
  "access": "<new-jwt-access-token>"
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

### AI / RAG Pipeline

All AI endpoints require a valid JWT in the `Authorization` header:

```
Authorization: Bearer <access-token>
```

---

#### `POST /app/ai/upload`

Ingest a file from S3 into the Qdrant vector store. The file must already exist in the configured S3 bucket.

**Access:** `editor` or `admin` role only

**Request body:**

```json
{
  "s3_key": "documents/report.pdf"
}
```

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

**Error responses:**

| Status | Reason |
|---|---|
| `400` | `s3_key` missing or empty |
| `409` | File already ingested — delete it first to re-ingest |
| `415` | Unsupported file type |
| `422` | No text could be extracted from the file |
| `502` | S3 download, extraction, or embedding failure |

---

#### `POST /app/ai/query`

Ask a natural language question over all ingested documents. Returns a grounded answer with source citations.

**Access:** Any authenticated user (`viewer`, `editor`, `admin`)

**Request body:**

```json
{
  "question": "What are the key findings in the Q1 report?",
  "top_k": 5
}
```

`top_k` is optional and defaults to the `RAG_TOP_K` environment variable (default: `5`).

**Response `200`:**

```json
{
  "answer": "According to the Q1 report [documents/report.pdf], the key findings are...",
  "sources": ["documents/report.pdf", "documents/summary.docx"],
  "chunks": 5
}
```

If no relevant documents are found:

```json
{
  "answer": "I don't have any relevant documents to answer that question.",
  "sources": [],
  "chunks": 0
}
```

---

#### `GET /app/ai/files`

List all files that have been ingested into the vector store.

**Access:** Any authenticated user

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

## Ingestion Pipeline

### Document Flow

```
POST /app/ai/upload  { s3_key: "report.pdf" }
        │
        ▼
  Extractor.extract_and_chunk()
        │
        ├── download_from_s3()  →  temp file (/tmp/tmpXXXX.pdf)
        │
        ├── LangChain loader
        │     .pdf  → PyMuPDFLoader      (page-aware)
        │     .docx → Docx2txtLoader
        │     .pptx → UnstructuredPowerPointLoader
        │
        ├── RecursiveCharacterTextSplitter
        │     chunk_size=800, chunk_overlap=150
        │
        └── List[Document]  (with source + bucket metadata)
                │
                ▼
        embed_and_store()
                │
                ├── BedrockEmbeddings (Titan Embed Text v2)
                │
                └── QdrantVectorStore.from_documents()
                        │
                        ▼
                  Qdrant Cloud collection
```

### Media / Video Flow

```
POST /app/ai/upload  { s3_key: "lecture.mp4" }
        │
        ▼
  Extractor.extract_and_chunk()
        │
        ▼
  transcribe_media()
        │
        ├── start_transcription_job()  (AWS Transcribe)
        │     - speaker diarisation enabled (up to 10 speakers)
        │     - polls every 5s, timeout 30 minutes
        │
        ├── fetch transcript JSON from S3
        │
        └── Document(page_content=transcript_text)
                │
                ▼
  RecursiveCharacterTextSplitter  →  List[Document]
                │
                ▼
        embed_and_store()  →  Qdrant Cloud
```

---

## Role-Based Access Control

Roles are implemented using Django's built-in `Group` model. Each user belongs to exactly one group.

| Role | Register | Login | Query | Upload | List Files | Admin Panel |
|---|---|---|---|---|---|---|
| `viewer` | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| `editor` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `admin` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**Permission classes:**

| Class | Grants access to |
|---|---|
| `IsAnyRole` | Any authenticated user (viewer, editor, admin) |
| `IsAdminOrEditor` | editor and admin only |
| `IsAdmin` | admin only |

JWT tokens have a **1-hour access token lifetime** and a **7-day refresh token lifetime**. Refresh tokens rotate on every use.

---

## Services Layer

### Extractor

`Services/Extractor.py` — the ingestion orchestrator.

```python
from Services.Extractor import extract_and_chunk

chunks = extract_and_chunk(bucket_name="my-bucket", s3_key="docs/report.pdf")
# Returns List[Document] ready for embedding
```

Automatically routes to the correct loader based on file extension. Each `Document` carries:
- `source` — original S3 key
- `bucket` — S3 bucket name
- `page` — page/slide number (documents)
- `job_name` — Transcribe job name (media)
- `media_type` — file extension without dot (media)

---

### Embedding

`Services/Ai_service/embedding.py` — Bedrock embeddings + Qdrant storage.

```python
from Services.Ai_service.embedding import embed_and_store, get_vector_store

# Store chunks
stored_count = embed_and_store(chunks)

# Retrieve for search
vector_store = get_vector_store()
results = vector_store.similarity_search("my question", k=5)
```

Uses **lazy singletons** for both the Bedrock client and the Qdrant client — connections are created once per process and reused. The Qdrant collection is created automatically if it doesn't exist.

---

### Video Transcription

`Services/Ai_service/video_transcibing.py` — AWS Transcribe integration.

```python
from Services.Ai_service.video_transcibing import transcribe_media

doc = transcribe_media(bucket_name="my-bucket", s3_key="videos/lecture.mp4")
# Returns a LangChain Document with the full transcript
```

- Generates a unique job name per transcription (`arishem-<uuid>`)
- Polls every 5 seconds, gives up after 30 minutes
- Speaker diarisation enabled (up to 10 speakers)
- Output JSON stored in `TRANSCRIBE_OUTPUT_BUCKET` under `transcripts/<filename>/`

---

### RAG Agent

`Services/agent.py` — retrieval + generation.

```python
from Services.agent import query

result = query("What is the main topic of the uploaded documents?", top_k=5)
# {
#   "answer": "...",
#   "sources": ["docs/report.pdf"],
#   "chunks": 5
# }
```

The agent uses a strict system prompt that instructs Claude to:
- Only use information from the retrieved context
- Say "I don't have enough information" if the answer isn't in the context
- Always cite the source document

LLM settings: `temperature=0.2`, `max_tokens=2048`.

---

## Data Models

### `User`

Extends Django's `AbstractUser`. Uses **email as the login identifier**.

| Field | Type | Notes |
|---|---|---|
| `id` | BigAutoField | Primary key |
| `email` | EmailField | Unique, used for login |
| `username` | CharField | Kept for Django admin compatibility |
| `groups` | M2M → Group | Role is derived from the first group |
| `is_active` | BooleanField | Disabled accounts cannot log in |

**Properties:**
- `user.role` — returns `"admin"`, `"editor"`, or `"viewer"` (defaults to `viewer`)
- `user.has_role("admin", "editor")` — returns `True` if the user has any of the given roles

### `IngestedFile`

Tracks every file successfully ingested into Qdrant.

| Field | Type | Notes |
|---|---|---|
| `id` | BigAutoField | Primary key |
| `s3_bucket` | CharField | S3 bucket name |
| `s3_key` | CharField | S3 object key |
| `file_type` | CharField | One of the `FileType` choices |
| `chunks_stored` | PositiveIntegerField | Number of vector chunks created |
| `ingested_at` | DateTimeField | Auto-set on creation |
| `transcribe_job` | CharField | AWS Transcribe job name (media only) |
| `uploaded_by` | FK → User | `SET NULL` on user deletion |

Unique constraint on `(s3_bucket, s3_key)` — prevents duplicate ingestion.

---

## Middleware

`app.middleware.RequestLoggingMiddleware` is active for all requests. It logs:

```
INFO 2024-01-15 10:30:00 middleware POST /app/ai/upload → 201  (245.3ms)
```

Log output goes to stdout (captured by Docker / your log aggregator). The logger name is `arishem.requests`.

---

## Docker

The `Dockerfile` uses a **multi-stage build**:

1. **Builder stage** — installs all Python dependencies (including C extensions like `mysqlclient`) into `/install/packages`
2. **Runtime stage** — copies only the compiled packages, no build tools, smaller final image

Security hardening:
- Runs as a non-root user (`arishem`)
- No compilers in the final image
- Static files collected at build time

**Gunicorn configuration:**

| Setting | Value | Override via |
|---|---|---|
| Workers | 2 | `WEB_CONCURRENCY` env var |
| Timeout | 120s | Dockerfile `CMD` |
| Bind | `0.0.0.0:8000` | Dockerfile `CMD` |

To scale workers in production, set `WEB_CONCURRENCY` in your ECS task definition or `docker-compose.yml`.

---

## CI/CD

GitHub Actions workflow at `.github/workflows/django.yml` runs on every push and pull request to `main`.

**Pipeline steps:**

1. Checkout code
2. Write `.env` file (from `ENV_FILE` secret if set, otherwise CI defaults)
3. Set up Python 3.12 with pip cache
4. Install system dependencies (`libmysqlclient-dev`, `gcc`)
5. Install Python dependencies
6. `python manage.py check --deploy` (non-fatal) + `python manage.py check`
7. `python manage.py migrate` (SQLite in-memory)
8. `python manage.py test --verbosity=2`

**CI uses SQLite in-memory** — no MySQL, Qdrant, or AWS credentials needed for the test run. All external service calls are mocked or skipped in tests.

To add real secrets for integration tests, create a `ENV_FILE` repository secret containing the full contents of your `.env` file.

---

## Security Notes

- **Never commit `.env`** — it is in `.gitignore`
- **Use IAM roles in production** — do not set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` on EC2/ECS
- **`DEBUG=False` in production** — the `check --deploy` step will warn you if it's not
- **`SECRET_KEY`** — generate a fresh one per environment, never reuse the example value
- **Passwords** — validated against Django's full password validator suite (similarity, length, common passwords, numeric-only)
- **JWT** — access tokens expire in 1 hour; refresh tokens rotate on every use
- **Database** — `DATABASE.py` is a one-time setup script for creating the RDS database. Remove or restrict it before deploying — it contains credentials and should never be run in production

---

## Supported File Types

### Documents
| Extension | Parser | Notes |
|---|---|---|
| `.pdf` | PyMuPDF | Fast, page-aware extraction |
| `.docx` | Docx2txt | Full text including tables |
| `.pptx` | Unstructured | Slide-aware extraction |

### Media (transcribed via AWS Transcribe)
| Extension | Type |
|---|---|
| `.mp4`, `.mov`, `.avi`, `.mkv` | Video |
| `.mp3`, `.wav`, `.flac`, `.ogg`, `.m4a` | Audio |

---

## Configuration Reference

### JWT Token Lifetimes

| Token | Lifetime | Configurable |
|---|---|---|
| Access | 1 hour | `settings.py` → `SIMPLE_JWT` |
| Refresh | 7 days | `settings.py` → `SIMPLE_JWT` |

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
