# Load test

What the query path does under concurrent load, what limited it, and what changed.

## Method

- **Stack:** the production containers and commands, with the production memory
  limits (Postgres 320 MB, Redis 96 MB, Qdrant 640 MB) and the API capped at 2 CPUs and
  1.2 GiB, run through Docker Desktop on a 12-core laptop. A `t4g.small` has 2 vCPUs
  and 2 GiB in total and shares them with every other service, so **absolute numbers
  here are optimistic; the shape is what carries over.**
- **LLM:** `fake_groq.py`, an OpenAI-compatible stand-in, instead of Groq. Groq's free
  tier allows 8,000 tokens a minute and one agentic query uses ~3,300, so against the
  real API the system tops out near 2 queries a minute and the test would measure
  Groq's quota. The stand-in sleeps 0.70–0.96 s per call, the range measured against
  the real API (6 calls, median 0.76 s). The application code is unmodified; only
  `GROQ_API_BASE` differs.
- **Traffic:** closed loop, no think time. N users means N requests in flight. Each
  sends one of the 53 answerable golden-set questions at random against a workspace
  holding the 9-document corpus. 60 s per level, after the users start.
- **Off during the test:** the answer cache (53 repeated questions would measure the
  cache), the per-workspace limit and the per-user throttles (one test user sends
  everything).

```
docker compose -f loadtest/docker-compose.loadtest.yml up -d --build
API_WORKER_ARGS="--workers 2 --worker-class gthread --threads 8" \
  docker compose -f loadtest/docker-compose.loadtest.yml up -d api
bash loadtest/run.sh threaded 1 2 4 8 16 32 64
```

## Results

Every request succeeded in every run (0 failures).

| Configuration | Users | Req/s | p50 ms | p95 ms | p99 ms |
|---|---|---|---|---|---|
| 2 sync workers (before) | 1 | 0.35 | 2,800 | 3,100 | 3,100 |
| | 4 | 0.71 | 5,500 | 6,100 | 6,100 |
| | 16 | 0.67 | 23,000 | 24,000 | 25,000 |
| | 32 | 0.69 | 30,000 | 44,000 | 44,000 |
| 2 workers × 8 threads (after) | 1 | 0.37 | 2,700 | 2,900 | 2,900 |
| | 4 | 1.42 | 2,700 | 3,000 | 3,000 |
| | 16 | 5.11 | 2,900 | 4,100 | 4,800 |
| | 32 | 5.37 | 5,700 | 7,300 | 8,000 |
| | 64 | 5.35 | 9,600 | 14,000 | 16,000 |
| 2 workers × 16 threads | 16 | 5.45 | 2,700 | 4,200 | 5,200 |
| | 32 | 6.56 | 4,400 | 6,900 | 7,700 |
| | 64 | 6.48 | 7,700 | 14,000 | 16,000 |

Raw per-level CSVs and the gunicorn command each run used are in `results/`.

## What limited it, in order

1. **Sync workers (0.69 queries/s).** A query is ~3 s, almost all of it waiting for the
   LLM, and a sync worker waits with it: 2 workers can have 2 queries in flight, so
   throughput is 2 / 3 s ≈ 0.7 whatever the demand. Latency at 32 users was 30 s
   because requests simply queued. Checked in isolation: 8 concurrent LLM calls took
   1.3 s, 8 concurrent `agent.query()` calls took 3.9 s, and 8 concurrent HTTP
   queries took 11.5 s, so the serialisation was in the gunicorn worker model, not
   the LLM client, the embedding model or Qdrant.
2. **Fix: `gthread`, 8 threads per worker.** 7.4× the throughput (0.69 → 5.1 queries/s
   at 16 users) with p50 unchanged at 2.9 s. Memory cost: ~140 MiB, because threads
   share their process's embedding model.
3. **The next limit is CPU (~5.4 queries/s).** With 8 threads the API container ran at
   ~200% of its 2 CPUs from 32 users up. Each query spends about 0.37 CPU-seconds
   (2 CPUs / 5.4 per s) in embedding the question, JSON, ORM work and the HTTP stack.
   Doubling threads to 16 gained 22% (6.5/s) and raised memory to the 1.17 GiB limit,
   so **8 threads is the setting shipped**: most of the gain, with memory headroom.
   More throughput past this point means more cores, not more threads.

## Reading this for a real deployment

- The numbers are for a stand-in LLM. Real Groq adds its rate limits, which the
  failover in `Services/agent.py` handles, and which cap a free-tier key at about 2
  queries a minute regardless of this system.
- A `t4g.small` shares its 2 vCPUs with Postgres, Qdrant, Redis and the worker, so
  expect well under the 5.4 queries/s here. That is still ~7× the 0.7 it would have
  managed before the change.
- Past saturation the system degrades by queueing (p50 9.6 s at 64 users), not by
  failing: no errors at any level.
- The per-workspace limit (`WORKSPACE_QUERY_RATE`, default 120/min) should be sized
  from this: capacity divided by the number of workspaces expected to be busy at once.

## Failure demo

`chaos_kill_worker.py` uploads a document and `SIGKILL`s the process ingesting it, the
signal the OOM killer sends. See the section below for the result.

### Result

`results/chaos_single_kill.txt`: a 1.1 MB document, `SIGKILL` to the process embedding
it. The file went PENDING → PROCESSING → (killed) → PROCESSING again, and finished
`SUCCESS` on its second delivery with 1,681 chunks. A second run (4.2 MB) finished
with 6,689 chunks, the same count as the same document ingested without interruption,
and the demo script checks that Qdrant holds exactly the recorded number of vectors,
so a retry does not duplicate. (The 4.2 MB runs were not saved as transcripts.)

Before this change the task was acknowledged on arrival, so a killed task was simply
lost and the file stayed in PROCESSING until the 30-minute reconcile job gave up on
it. It now uses late acknowledgement, a redelivery cap
(`MAX_INGESTION_ATTEMPTS`, covered by unit tests, not by a demo) and the reconcile
job as the last resort.

**The demo also found a bug.** The replacement process loads the embedding model
before reporting ready, which takes longer than Celery's 4 s default, so the parent
killed each replacement in turn and the worker never recovered. Fixed with
`CELERY_WORKER_PROC_ALIVE_TIMEOUT = 120`.
