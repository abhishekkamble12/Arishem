# Deploying Arishem to AWS

One CloudFormation stack puts the whole system on a single small EC2 instance:
Postgres, Redis and Qdrant as containers, documents in S3, Caddy terminating TLS.

## What it costs

Prices below are the live on-demand rates for **ap-south-1 (Mumbai)**, read from
the AWS Pricing API on 2026-10-26. They are list prices, not a bill you have seen.

| Item | Rate | Monthly |
|---|---|---|
| EC2 `t4g.small` (2 vCPU, 2 GiB, ARM) | $0.0112/hr | **$8.18** |
| EBS gp3 root volume, 30 GiB | $0.0912/GB-mo | **$2.74** |
| Public IPv4 address (in use) | $0.005/hr | **$3.65** |
| S3 Standard, ~5 GiB of documents | $0.025/GB-mo | **$0.12** |
| EBS snapshots, 7 daily, ~8–10 GB in use (estimate) | $0.05/GB-mo | **≈ $0.50** |
| CloudWatch: 6 custom metrics, 7 alarm metrics, < 0.1 GB of logs (see below) | $0.30 / $0.10 / $0.67 per GB | **$0.00–2.57** |
| CloudFormation, IAM, Budgets, Parameter Store, Session Manager, DLM, SNS email | — | **$0.00** |
| | | **≈ $15.19–17.76/month** |

The CloudWatch line is a range because CloudWatch's always-free allowance (10 custom
metrics, 10 alarms, 5 GB of logs a month) covers all of it on an account that uses
nothing else; at list price it is 6 × $0.30 + 7 × $0.10 + about $0.07 of logs.

The snapshot line is the only other estimate: the $0.05/GB-month rate comes from the
Pricing API, but the GB is a guess at how much of the 30 GiB volume the OS, the
Docker images and the data actually occupy. Snapshots are incremental and bill only
for blocks in use.

Notes that actually matter for the bill:

- **Data transfer out** is the usual surprise. The first 100 GB/month across AWS
  is free, which a demo will not come close to.
- **Stopping the instance** saves the $8.18 but not the volume or the IP, so an
  idle stack still costs about $6.40/month. Delete the stack to stop all of it.
- **The address is billed even when idle**, so a stopped instance with an Elastic
  IP keeps charging. This is why the stack has no "pause" button worth using.
- Choosing `t3.small` instead doubles the compute line to $16.35 and takes the
  total to roughly $22.86. Only do that if you need x86.

The stack creates an **AWS Budget** that emails you at 80% of actual and 100% of
forecast spend. That is a notification, not a cap: AWS will not stop the
resources for you.

## Why this shape

The expensive habits in a "production" AWS diagram are a load balancer (~$16/mo),
a NAT gateway (~$32/mo), RDS (~$12/mo and up) and ElastiCache. This stack has none
of them, and for a system with one instance it loses nothing real:

- **No ALB.** Caddy on the box terminates TLS and gets a free Let's Encrypt
  certificate. A load balancer with one target behind it is just a bill.
- **No NAT gateway.** The instance sits in a public subnet with a security group
  that allows only 80 and 443 inbound.
- **No RDS or ElastiCache.** Postgres and Redis are containers on the same box
  with a persistent volume.
- **No SSH port and no key pair.** Shell access is through SSM Session Manager,
  which is audited and needs no open port.
- **Secrets live in SSM Parameter Store** as SecureStrings. They are not in the
  template, the AMI, the repository or the instance's user data.

When you outgrow it: move Postgres to RDS, Qdrant to Qdrant Cloud, and put the
API behind an ALB with an autoscaling group. The compose file is the seam.

## Deploying

Prerequisites: the AWS CLI, credentials in the repository `.env`, and a
`GROQ_API_KEY` in the same file.

```powershell
./deploy/deploy.ps1 -AlertEmail you@example.com
```

The script stores the secrets in Parameter Store, generates a production
`SECRET_KEY` the first time (and reuses it afterwards, so sessions survive a
redeploy), then creates the stack. First run takes 15–30 minutes, most of it
building the backend image, since torch and the embedding model are large.

The stack only reports success once the API answers its own health check, so a
`CREATE_COMPLETE` means the application is actually running.

Useful switches:

| Switch | Default | Why |
|---|---|---|
| `-Region` | `ap-south-1` | Closest to you; change it and the price table moves. |
| `-InstanceType` / `-Architecture` | `t4g.small` / `arm64` | Keep these consistent: `t4g.*` is arm64, `t3.*` is x86_64. |
| `-DomainName` | none | With DNS already pointing at the stack's Elastic IP, Caddy issues a certificate and the site becomes HTTPS. |
| `-MonthlyBudgetUSD` | `20` | Above the ~$15 steady state, so 80% is a warning. |

## After it is up

```powershell
# the site, the bucket, and a shell command
aws cloudformation describe-stacks --stack-name arishem `
  --query 'Stacks[0].Outputs[].[OutputKey,OutputValue]' --output table

# shell on the box, no SSH
aws ssm start-session --target <InstanceId> --region ap-south-1

# on the box
cd /opt/arishem
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api
cat /var/log/arishem-bootstrap.log     # what happened at first boot
```

### Monitoring and alarms

The API and worker send their stdout to the CloudWatch log group in the stack's
`LogGroup` output, through Docker's `awslogs` driver. Metrics ride along in those
logs as Embedded Metric Format lines (`backend/app/observability.py`), so there is
no agent to install and nothing on the request path calls the CloudWatch API.

| Alarm | Fires when | Why this signal |
|---|---|---|
| Query latency | p95 over 10 s in 2 of 3 five-minute periods | what users feel first |
| Query error rate | over 5% of queries fail, in 2 of 3 periods with 10+ queries | at demo traffic, one failure in three queries would otherwise page you |
| Ingestion stuck | a document has waited over 15 minutes | the age of the oldest item, not the queue length: a long queue that moves is load |
| Worker heartbeat | no queue metrics for 10 minutes | the worker publishes every minute, so silence means it is down, while every API request still succeeds |
| Host failure | EC2 system status check fails | **recovers** the instance onto new hardware: same volume, same IP |
| Instance unresponsive | EC2 instance status check fails for 3 minutes | **reboots** it |

All six email `AlertEmail` through an SNS topic. **AWS sends a subscription
confirmation email after the first deploy; until you click it, alarms reach nobody.**

```powershell
# what the alarms see
aws cloudwatch get-metric-statistics --namespace Arishem --metric-name QueryLatency `
  --dimensions Name=Service,Value=api --extended-statistics p95 --period 300 `
  --start-time (Get-Date).AddHours(-1).ToUniversalTime().ToString("o") `
  --end-time (Get-Date).ToUniversalTime().ToString("o") --region ap-south-1
aws cloudwatch describe-alarms --alarm-name-prefix arishem --region ap-south-1 `
  --query 'MetricAlarms[].[AlarmName,StateValue]' --output table
```

The alarms are validated (`cfn-lint` and `aws cloudformation validate-template`) but
were added after the one live deployment, so none has fired on a real stack yet.

### Adding a domain

1. Point an A record at the stack's `ElasticIPAddress` output.
2. Redeploy with `-DomainName yourdomain.com`.

Caddy requests the certificate on start, so DNS must resolve first.

### Turning on Google sign-in

The code is already in place on both sides: the React button, the `/app/auth/google`
endpoint that verifies the ID token, and the account-linking rules (verified email
only, case-insensitive match). What it needs is an OAuth client that Google will
accept requests from.

**Google will not accept the IP-only deployment.** Authorised JavaScript origins
must be `https://` on a real domain; plain `http://` is allowed only for
`localhost`, and raw IP addresses are rejected outright. So Google sign-in in
production needs the domain and certificate from the previous section first.

1. Google Cloud console → **APIs & Services → Credentials → Create credentials →
   OAuth client ID**, type **Web application**. (Or open the existing client whose ID
   is in `frontend/.env`.)
2. Under **Authorised JavaScript origins** add `http://localhost:5173` for local
   development and `https://yourdomain.com` for production. The button uses origins,
   not redirect URIs, so the redirect list can stay empty.
3. Put the client ID in `frontend/.env` as `VITE_GOOGLE_CLIENT_ID` and in
   `backend/backend/.env` as `GOOGLE_CLIENT_ID`. They must be the same value: the
   backend rejects any token whose audience is not this client.
4. For a deployment, pass it through: `./deploy/deploy.ps1 -AlertEmail … -DomainName
   yourdomain.com -GoogleClientId <client-id>`. It is baked into the frontend at
   build time, because Vite inlines environment variables, so a change needs a
   rebuild rather than a restart.

The client ID is a public identifier, not a secret; it is visible in the browser
anyway. There is no client secret in this flow, because the backend only verifies a
signed ID token. If the button shows `origin_mismatch`, the origin in step 2 is
missing or does not match the address bar exactly, including the port.

### Backups and restoring

A Data Lifecycle Manager policy snapshots the instance's volume every day at
20:30 UTC and keeps the last `BackupRetentionDays` (default 7). Postgres, Qdrant and
the Docker volumes all live on that one volume, so one snapshot covers everything.

The snapshots are crash-consistent: the same state as pulling the power. Postgres
and Qdrant both replay their write-ahead logs on start, so a restored volume comes
back the way a server does after an outage, without a separate dump step.

To restore, take the newest snapshot, create a volume from it, and swap it in:

```powershell
aws ec2 describe-snapshots --owner-ids self --region ap-south-1 `
  --filters Name=tag:arishem-backup,Values=arishem `
  --query 'sort_by(Snapshots,&StartTime)[-1].[SnapshotId,StartTime]' --output table
# Stop the instance, detach its root volume, create a volume from the snapshot in
# the same Availability Zone, attach it as /dev/xvda, and start the instance.
```

This has been validated as a template (`validate-template`, `cfn-lint`). It has
not yet run on a deployed stack, so the first scheduled snapshot is unobserved.

### Tearing it down

```powershell
aws cloudformation delete-stack --stack-name arishem --region ap-south-1
```

Two things outlive the stack and keep billing until you remove them:

```powershell
# 1. The bucket is Retain, so your documents survive.
aws s3 rb s3://<DocumentsBucketName> --force

# 2. Snapshots are kept when the policy that made them is deleted.
aws ec2 describe-snapshots --owner-ids self --region ap-south-1 `
  --filters Name=tag:arishem-backup,Values=arishem --query 'Snapshots[].SnapshotId' --output text
aws ec2 delete-snapshot --snapshot-id <id> --region ap-south-1   # once per id
```

## Known gaps

- **The refusal threshold is a weak, corpus-dependent signal.** The default, 0.065,
  was fitted on a three-document corpus where the previous 0.35 refused 27 of 28
  answerable questions. On the nine-document hard suite, answerable and plausible
  unanswerable questions overlap in confidence, so no threshold separates them, and
  the threshold mainly stops clearly off-topic questions. Confidence is the *mean* of
  the top-k, which drifts with corpus size. Watch `confidence` and the `refused` flag
  in `PredictionLog` as a real corpus grows, and rerun `evals/run_eval.py` before
  moving the threshold.
- **One instance is one point of failure, by design.** A reboot is downtime. The
  host-failure and instance-check alarms recover or reboot the instance on their
  own, and the daily snapshots cover data loss, but there is no second box.
  Removing that means an Auto Scaling group behind a load balancer, with Postgres
  and Qdrant moved off the instance to managed services: roughly $30–60 a month
  more for a system with no users yet.
- **Backups lose up to a day.** One snapshot a day bounds data loss at 24 hours.
