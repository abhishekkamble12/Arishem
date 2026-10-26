# Deployment verification

A record of `deploy/cloudformation.yml` being deployed to AWS and tested over the
network. The stack was deleted afterwards, so the URL below is dead — it is quoted
so the run is identifiable, not so you can visit it.

| | |
|---|---|
| Date | 2026-10-26 |
| Region | ap-south-1 (Mumbai) |
| Instance | `t4g.small` (2 vCPU, 2 GiB, **arm64**) |
| Stack | `arishem`, created from `main` at commit `9770ffc` |
| Site | `http://13.127.234.71` (deleted) |
| Bucket | `arishem-docs-989200478098` (deleted) |

`CREATE_COMPLETE` is itself a test: the template's `CreationPolicy` only signals
success once the instance's own `curl` against `/app/health` returns 200, so the
stack cannot report success while the application is down.

## What the box looked like

```
$ docker compose -f docker-compose.prod.yml ps
api       Up 2 minutes (healthy)
postgres  Up 2 minutes (healthy)
qdrant    Up 2 minutes
redis     Up 2 minutes (healthy)
web       Up 2 minutes
worker    Up 2 minutes

$ free -m
               total        used        free      shared  buff/cache   available
Mem:            1840        1368          81          11         391         292
Swap:           4095         320        3775

$ uname -m
aarch64
```

Two things worth taking from that:

- **The ARM build works.** `aarch64` with a working stack means torch and
  sentence-transformers installed from PyPI's aarch64 wheels, which is what makes
  the \$8.18/month `t4g.small` usable instead of the \$16.35 x86 equivalent.
- **2 GiB is genuinely tight.** 292 MB available and 320 MB of swap in use. The
  template's 4 GB swap file is not decoration — without it the image build runs
  out of memory. Under any real traffic, move to `t4g.medium`.

## What was tested, over the network

32 checks, all passing. Run with
`python verify_live.py http://<ip> <bucket>` (the script lives outside the repo;
it is a thin HTTP client plus `boto3` for the S3 assertions).

```
--- the site is actually up ---
  PASS  health returns 200
  PASS  health reports the database reachable
  PASS  the frontend is served
  PASS  the SPA router catches unknown paths

--- security headers and config ---
  PASS  no Django debug page leaks (DEBUG is off)
  PASS  unconfigured Google sign-in answers 503, not 500
  PASS  unauthenticated access is rejected

--- accounts and per-workspace roles ---
  PASS  sign-up makes you admin of your own workspace
  PASS  a shared workspace can be created
  PASS  a member can be added as viewer
  PASS  a viewer cannot upload

--- ingestion through the deployed worker into S3 ---
  PASS  upload accepted (202)
  PASS  storage key is namespaced to the workspace
  PASS  object landed in the stack's real S3 bucket
  PASS  the Celery worker ingested it from S3
  PASS  chunks were embedded into Qdrant

--- retrieval, answer, citations (real Groq on the instance) ---
  PASS  query returns 200
        answer (16.0s): Business records are kept for seven years from the end of the
        financial year in which they were created, and the destruction of any record
        must be signed off by the Data Protection Officer.
        confidence=0.69514084 usage={'llm_calls': 3, 'prompt_tokens': 1041, 'completion_tokens': 449}
  PASS  answer states the seven-year retention
  PASS  answer names the sign-off authority
  PASS  citations are returned
  PASS  token usage is reported
  PASS  the question was not refused

--- out-of-domain refusal at the calibrated threshold ---
        confidence=-0.05447039 refused=True
  PASS  an unrelated question is refused

--- tenant isolation across the network ---
  PASS  another tenant cannot read this workspace
  PASS  another tenant cannot query it
  PASS  another tenant cannot delete its files

--- cost tracking ---
  PASS  monitoring returns 200
        {'total_predictions': 2, 'llm_calls': 4, 'prompt_tokens': 1281,
         'completion_tokens': 515, 'refused_queries': 1,
         'estimated_cost_usd': 0.0, 'cost_rates_configured': False}
  PASS  tokens were accumulated
  PASS  the refusal was counted
  PASS  cost reads $0.00 with no rates configured

--- delete removes the S3 object too ---
  PASS  owner can delete their file
  PASS  the S3 object is gone

32 passed, 0 failed
```

## Measurements from the deployed system

These supersede the figures taken on a development machine, because they include
real network latency, a real S3 round trip and the instance's own CPU.

| | |
|---|---|
| Answered query, end to end | **16.0 s** (agentic mode, 3 Groq calls) |
| Retrieval confidence, in-domain | **0.695** |
| Retrieval confidence, out-of-domain | **-0.054**, refused |
| Tokens, one answered query | **1,041 in + 449 out** |
| Tokens, one refused query | 240 in + 66 out (the difference between the two rows above) |

16 seconds is slow for a chat interface, and the cause is agentic mode making
three sequential LLM calls. Setting `RAG_AGENTIC_MODE=false` trades the
decomposition and self-critique steps for roughly a third of the latency. That
trade has not been measured for answer quality yet.

## Bugs this exercise found

Deploying for real surfaced three defects that local testing had not:

1. `aws ssm get-parameter` writes to stderr when a parameter is absent, and
   Windows PowerShell turns a native command's stderr into a terminating error
   under `ErrorActionPreference = 'Stop'`. The first-run path of `deploy.ps1`
   therefore always died. Replaced with `describe-parameters`, which succeeds
   with empty output.
2. `RandomNumberGenerator::Fill` is .NET Core only. Windows PowerShell 5.1 runs
   on .NET Framework and threw `MethodNotFound`, so the script could never
   generate a production `SECRET_KEY`. Replaced with `Create().GetBytes()`,
   which exists on both.
3. Compose passed the cost rates through as empty strings, and settings casts
   them with `float()`, which raises on `""`. An unset rate would have stopped
   the container from starting. They now default to `0`.

Both PowerShell bugs failed safely — the script exited before creating anything,
confirmed each time by checking for stacks, SSM parameters and buckets.

## Teardown

```powershell
aws cloudformation delete-stack --stack-name arishem --region ap-south-1
aws s3 rb s3://arishem-docs-989200478098 --force   # the bucket is Retain-on-delete
```

Billing for this run was a few hours of `t4g.small`, an EBS volume and one public
IPv4 address — well under a dollar.
