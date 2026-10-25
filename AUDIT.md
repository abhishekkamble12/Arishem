# AUDIT — Arishem (Phase 1, no code changed)

> Snapshot taken before any fixes. Later phases address items listed here; `git log upgrade/tier1` shows which. One correction: the frontend `npm run build` did **not** fail; its type-check silently checked nothing (fixed in `ccc11d2`).

Audited: whole backend, Dockerfile/compose/CI, evals, docs, git history, and the frontend structure.
Frontend pages were skimmed for stale claims and API wiring, not line-reviewed.

**How this was verified, and what wasn't**
- The local `.venv` is broken (`google-auth` is not installed), so I could not run the test suite here. The existing `docs/INTERVIEW_PREP.md` says 44 tests passed on 2026-10-22; I count 44 `def test` in the three test files, which matches, but I have not reproduced the pass. I will fix the environment at the start of Phase 2 and show real output.
- No linter is configured, so there is no lint output to show.
- Nothing was executed against Groq/Qdrant; every performance and eval number in the repo is unverified by me.

---

## 1. What it does (10 lines)

1. Multi-tenant RAG service: users belong to **workspaces**, upload PDF/DOCX/PPTX/audio/video, then ask questions answered only from that workspace's files, with citations.
2. **API:** Django 5.1 + DRF function views, SimpleJWT auth (+ Google/GitHub login), roles via Django Groups (viewer/editor/admin).
3. **Ingestion:** `POST /upload-direct` → file saved to local disk → `IngestedFile(PENDING)` row → Celery task (extract → 800/150 char chunks → MiniLM embeddings → Qdrant) → `SUCCESS/FAILED`. Beat job fails rows stuck >30 min.
4. **Query:** embed question → Qdrant top-k with `workspace_id` payload filter → if mean similarity < 0.35 refuse without calling the LLM → else Groq Llama-3.3-70B answers in JSON with citations.
5. **Agentic mode (default ON):** LLM decomposes the question (≤4 sub-queries), retrieves per sub-query, synthesises, self-critiques, retries once. Up to 4 LLM calls per question. Falls back to single-pass on any error.
6. **Meetings:** YouTube URL or recording → yt-dlp/ffmpeg → local faster-whisper → LLM title/summary/action items.
7. **Observability:** every query logged to `PredictionLog`; a rolling-confidence "drift" check emails admins.
8. **Eval:** `evals/run_eval.py` runs 30 golden questions through the real pipeline against an in-memory Qdrant and scores with RAGAS.
9. **Deploy shape:** Docker image + compose (redis, migrate, api, celery, beat). DB is SQLite or MySQL; Qdrant and Groq are external.
10. **Frontend:** React 18 + TS + Tailwind + Zustand, ~13 pages (landing, auth, chat, documents, upload, meetings, monitoring, dashboard, settings, profile, workspace selector).

---

## 2. Scorecard (0–10, blunt)

| Dimension | Score | Why |
|---|:-:|---|
| Code quality | 5 | Readable, commented, sensible helpers (`is_key_in_workspace`, `resolve_workspace`). Dragged down by misnamed modules (`aws_storage` = local disk, `video_transcibing`), 4 copies of JSON-fence stripping, 350-line orchestration functions, `except Exception` in ~34 places, duplicated Google/GitHub login bodies. |
| Structure | 5 | `Services/` + `app/` split is fine, but one flat `views.py` (626 lines), `Services` isn't a proper package (path hack in `settings.py`), stray scripts in `backend/` root, nested git repo. |
| Error handling | 6 | Better than most freshers: state machine, idempotent tasks, ordered deletes, 502/409 where right. Missing: LLM timeout/retry, input validation (see below), consistent error shape. |
| Testing | 5 | 44 offline tests with fakes, tenant-isolation and RBAC covered — genuinely good. But no coverage gate, no lint/type step, README's "~58% coverage" is unverified, no tests for the Whisper/meeting path or frontend. |
| Security | 4 | Tenant filter, RBAC, path-traversal guard are solid. **Leaked DB password in git history**, CORS allow-all with credentials, no login/register throttling, no upload size cap, no prompt-injection guard, task-status endpoint has no ownership check. |
| Performance | 3 | Zero measurements in the current architecture. `benchmark.md` is from the old Bedrock/Titan stack on 3 queries. Up to 4 serial LLM calls per question, no streaming, no caching, drift check on the request path, per-process in-memory throttle. |
| Docs | 6 | README is honest and well organised, with real trade-offs. But stale claims elsewhere (frontend says "AWS Bedrock", `REAL_TEST_METRICS.md` is Titan-era), no architecture doc, eval numbers unreproducible. |
| Deployability | 4 | Dockerfile is decent (multi-stage, non-root). But: one image bundles torch + whisper + unstructured (very large), compose has **no Qdrant, no DB, no frontend**, so "`docker compose up` runs everything" is false; local-disk storage ties API and worker to one host; no live URL; `pyproject.toml` (django>=6) contradicts `requirements.txt` (5.1.4). |
| AI-engineering depth | 6 | Real strengths: confidence-gated refusal, agentic decompose/critique with graceful fallback, a golden set, RAGAS. Weak: no baseline comparison, no retrieval metrics (hit-rate/MRR), same-family judge, no prompt versioning, no cost/latency tracking. |
| Recruiter wow factor | 4 | Repo reads well but there is no live demo, no GIF, and a stranger who registers **cannot use the product** (see weakness #2). Breadth (meetings, YouTube, OAuth, monitoring) dilutes the one thing that is good. |

---

## 3. Top 10 weaknesses, by interview / recruiter impact

1. **A live RDS password is in public git history.** `backend/backend/DATABASE.py` (commits `dedab48`, `a3797fd`) hardcodes an RDS host, admin user and password; it has been pushed to `origin/main`. First thing any reviewer who clones and greps will find. Fixing the file isn't enough: the password must be rotated and history rewritten (see §4).
2. **A stranger can't use the app.** `RegisterSerializer` makes every signup a *viewer* in a fresh empty workspace; viewers can't upload (`IsAdminOrEditor`). So a public deploy would show people an empty chat box that can only refuse. For a demo, you need a seeded shared workspace or self-service upload for your own workspace.
3. **No live deployment / no demo.** "Deployed live and used by strangers" is currently 0%. Compose omits Qdrant, a database and the frontend; files live on a local volume; image includes torch + whisper + unstructured.
4. **Eval claims aren't defensible.** `SCORECARD.md` (faithfulness 0.92 etc.) is dated 2026-08-11, *before* the 2026-08-12 embedding switch to MiniLM, and I can't confirm it was produced by the current code. Four-decimal RAGAS means over 30 questions with a same-family judge, no baseline, no retrieval-only metrics. An interviewer asking "what was the baseline, and what does 0.92 mean?" has no answer. Also `benchmark.md` / `REAL_TEST_METRICS.md` describe a stack you no longer run (Titan 1024-dim).
5. **No cost/abuse guards on the expensive path.** Unbounded `top_k` from the client, no max question length, no upload size limit, `login`/`register` unthrottled, throttle is `LocMemCache` (per Gunicorn process, resets on deploy), all four metered endpoints share one bucket, agentic mode multiplies LLM calls by up to 4 with no per-request token/cost accounting or monthly cap.
6. **LLM reliability is thin.** No timeout, retry/backoff or fallback provider on `ChatGroq`; JSON parse failure falls back to returning raw text as the "answer"; prompt injection is unmitigated (retrieved text is concatenated into the prompt with no delimiters or instruction hierarchy); the self-critique judge shares the generator's model.
7. **CORS `ALLOW_ALL_ORIGINS=True` with credentials**, `check --deploy` is run in CI with `|| true`, no `SECURE_*` / HSTS settings, `GET /ai/tasks/<id>` returns any task's result/exception text to any logged-in user.
8. **Roles are global, not per workspace.** `User.role` is the first Django Group. A user who is admin is admin in every workspace they join; `set_user_role` lets an admin change *any* user's role. Fine for a demo, but "multi-tenant RBAC" is a claim an interviewer will probe.
9. **Stale/misleading UI and docs.** Frontend still says "AWS Bedrock (Titan V2)" and "Failed to reach S3 or Bedrock"; `README` calls the CI badge "Django CI" but CI doesn't lint/type-check; README says "Docker Compose ... runs Redis, migrate, API, worker, beat" but the app still needs external Qdrant + `.env`; `.txt`/`.md` can't be ingested in production though the eval corpus uses them.
10. **Code-quality tells.** Same fence-stripping block copy-pasted 4×; `hash()` for dedupe; 626-line `views.py` doing validation, orchestration and response shaping; `ensure_collection_exists()` called on every vector-store access and **deletes/recreates the collection on any verification error** (a transient Qdrant error could wipe all tenants' vectors); no pinned lockfile used by Docker (`uv.lock` and `requirements.txt` disagree).

> #10's collection-recreate behavior is the scariest correctness bug. See `Services/Ai_service/embedding.py` `ensure_collection_exists`: the `except` on `get_collection` deletes the collection "to be safe".

---

## 4. Embarrassments checklist

| Item | Status |
|---|---|
| Committed secrets | **YES.** RDS password in `backend/backend/DATABASE.py` history (`dedab48`, `a3797fd`); `YOUR_SECRET` placeholder also appears. No real `.env` was ever committed. No AWS/Groq-key patterns found in history. |
| Committed binary data | **YES.** `backend/database-1`, `database-1` are SQLite files (users, password hashes) committed in `60a3412`/`fd976a6`; a user's PDF (`Unit 5_Testability…pdf`) was committed under `backend/local_storage/`. All are staged for deletion in the working tree but remain in history. |
| `.gitignore` | Exists now, but `.gitignore` itself and 42 other changes are **uncommitted**; `.gitignore` ignores `database*` which would also match legit files. |
| Uncommitted work | **42 modified/deleted files**, new tests and `docs/` untracked. `main` on GitHub does not reflect the repo described in the README. Commit messages include `"Your commit message here"` (×2), `"abc testing"`, `"changed"`, `"Update fmt.Println … Goodbye"` (a Go snippet in a Python repo). |
| Dead code / stray scripts | `check_groups.py`, `setup_db.py`, `test_api.py`, `run_real_rag_test.py` in `backend/` root; empty `backend/backend/frontend.md`; `.kiro/` spec folder; `powershell.exe` (495 KB binary) in the parent repo; parent repo tracks `Arishem` as a broken gitlink. |
| Giant files | `views.py` 626, `agent.py` 371, `agentic.py` 289, `run_eval.py` 286, several 350–500-line React pages with inline everything. |
| No tests | No — 44 backend tests exist. **No frontend tests**, no lint/type CI. |
| Unpinned deps | `qdrant-client>=`, `sentence-transformers>=`, `faster-whisper>=`, `boto3>=`, `yt-dlp>=`, `pydub>=`, `urllib3<2.0.0` (blocks security updates). Root `pyproject.toml` is out of sync with `requirements.txt`. |
| Bare/broad excepts | No bare `except:`; ~34 `except Exception` sites in non-test code, a couple swallow errors silently (`except Exception: pass`). |
| `print` debugging | None in the app code (only in the standalone scripts). Logging is plain-text, not structured, no request IDs. |
| `INTERVIEW_PREP.md` | `docs/INTERVIEW_PREP.md` is **untracked and not gitignored**; it contains candid "don't claim this" notes and would go public on the next `git add .`. |

### How to fix the leaked secret (do this regardless of anything else)
1. **Rotate now:** change the RDS master password in the AWS console (or delete the instance if it is a throwaway) and check CloudTrail/RDS logs for foreign logins. Assume it is already compromised: the repo is public.
2. Rewrite history to drop the files: `git filter-repo --invert-paths --path backend/backend/DATABASE.py --path backend/database-1 --path database-1 --path "backend/local_storage"`, then force-push. (Rewrites all commit SHAs; tell collaborators/forks.) Rewriting history is outward-facing, so I will not do it without your explicit go-ahead.
3. Add `gitleaks` to pre-commit and CI so it can't recur.

---

## 5. Verdict: deploy it, but cut scope

Worth deploying, and worth finishing — the **core is better than a typical fresher RAG project**: tenant-filtered retrieval, refusal gating before the LLM, a status state machine with idempotent tasks and ordered deletes, offline tests that cover isolation. Those are real engineering decisions you can defend.

But it is currently a feature pile (OAuth, YouTube meetings, Whisper, drift emails, monitoring dashboard, 13 pages) wrapped around a core that has no baseline, no latency/cost numbers and no running instance. For SDE/AI-eng roles, depth on one flow beats breadth. Ship the **ask-questions-over-documents flow** with measured quality, cost and latency, on a free-tier host with a seeded demo workspace.

**Hosting reality check (decision for you in Phase 5):** the Whisper/yt-dlp/torch stack will not fit a free 512 MB host. Cutting meetings removes most of that weight and makes free-tier hosting viable.

---

## 6. The one or two upgrades that matter most

1. **A real, reproducible evaluation (`make eval`)** — retrieval hit-rate@k and MRR on the labelled set, with a baseline (e.g. dense-only vs. dense + BM25 or reranker; agentic vs. single-pass), answer faithfulness, refusal precision/recall on out-of-domain questions, and tuning of the 0.35 threshold on the data rather than by feel. This directly feeds resume bullets with honest numbers, and is the answer to "how do you know it works?"
2. **Reliability + cost/latency layer around the LLM path** — timeouts, retries with backoff, fallback to single-pass/another model, input-length and injection guards, per-request token/cost/latency logging with p50/p95, a monthly spend cap, and a seeded demo mode so the live URL survives key exhaustion. This is what separates a demo from a service strangers can't bankrupt.

### Cut list (remove or hide — each adds noise or hosting weight)

| Cut | Why |
|---|---|
| YouTube/meeting intelligence (`Services/meeting/`, `ingest_youtube`, `MeetingAnalysis`, MeetingsPage, whisper/yt-dlp/pydub deps) | Biggest hosting-weight driver; unrelated to the RAG story; never evaluated. Move to a branch or tag. |
| Google + GitHub OAuth (`auth_social_views.py`, callback page) | Duplicated code, untested, not needed when email/password + a demo account exist. |
| Drift emails / `alerting.py` / `DriftLog` | The threshold-on-mean-confidence "drift" is statistically weak; keep `PredictionLog` and a simple stats endpoint. |
| Unstructured/PPTX loader | Heavy dependency for a rare format; keep PDF, DOCX, TXT, MD. |
| `Dashboard`/`Settings`/`Profile` pages, landing page effects | Keep: Login, Workspace, Documents, Chat. The rest is polish on a product that isn't live. |
| Root scripts (`check_groups.py`, `setup_db.py`, `test_api.py`), `.kiro/`, `backend/frontend.md`, parent-repo `powershell.exe` | Dead weight. |
| `REAL_TEST_METRICS.md`, `reports/benchmark.md`, `reports/test_run.txt` | Describe a retired stack; replace with eval output generated by one script. |

**Keep and showcase:** workspace-filtered retrieval, refusal gating, agentic-with-fallback (as an *evaluated* option against the single-pass baseline), ingestion state machine, RBAC tests.

---

## Decisions I need from you before Phase 2

1. **The dirty working tree.** 42 uncommitted changes (including staged deletions and the new `docs/`) sit on top of `main`. I created `upgrade/tier1` from it, unchanged. Should I commit that cleanup as the branch's first commits (grouped by theme), or do you want to review it first?
2. **Secret leak:** OK to prepare the `git filter-repo` command for you to run after you rotate the password? (I won't rewrite or force-push on my own.)
3. **Scope:** approve the cut list above (esp. meetings, OAuth, drift email)? Or keep any of them?
4. **Storage/DB for deploy:** keep local-disk storage (simplest; API and worker on one host) or move to S3-compatible object storage (e.g. Cloudflare R2)? And Postgres vs. MySQL — Postgres has free tiers (Neon/Supabase), MySQL does not; I recommend Postgres.
5. **`docs/INTERVIEW_PREP.md`:** it already exists (untracked). I'll add it to `.gitignore` in Phase 2 and regenerate it in Phase 7 from the final code. OK?
