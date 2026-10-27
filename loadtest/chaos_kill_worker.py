"""
Failure demo: kill the Celery process that is ingesting a document, and show what
happens to the document. Runs against the load-test stack (docker-compose.loadtest.yml).

    python loadtest/chaos_kill_worker.py

One kill: the task is redelivered and finishes. Do not raise --kills to demonstrate
the attempt cap: the script cannot tell a task attempt from a replacement process
that is still loading its model, so extra kills land on the wrong target (tried;
the cap is covered by a unit test instead).

The process killed is the prefork child doing the work, with SIGKILL, which is what
the Linux OOM killer sends when a 2 GiB box runs out of memory. Its parent survives
and notices. Every step is printed with a timestamp, so the output is the record.
"""

import argparse
import os
import subprocess
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
COMPOSE = ["docker", "compose", "-f", os.path.join(HERE, "docker-compose.loadtest.yml")]
API = os.environ.get("LOADTEST_API", "http://localhost:18000")
EMAIL, PASSWORD = "chaos@example.com", "chaos-Passw0rd!"
T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def compose(*args, check=True):
    return subprocess.run([*COMPOSE, *args], capture_output=True, text=True, check=check).stdout


# Children of the worker's main process (PID 1 in its container), busiest first. The
# beat scheduler is a child too, but it is idle; the one embedding text is not.
FIND_BUSY_CHILD = """
import os
kids = []
for pid in filter(str.isdigit, os.listdir('/proc')):
    try:
        stat = open(f'/proc/{pid}/stat').read().rsplit(')', 1)[1].split()
    except OSError:
        continue
    if stat[1] == '1':
        kids.append((int(stat[11]) + int(stat[12]), int(pid)))
print(max(kids)[1] if kids else '')
"""


def busy_child_pid():
    return compose("exec", "-T", "worker", "python", "-c", FIND_BUSY_CHILD).strip()


def big_document(path, megabytes):
    """Real policy text repeated with numbered sections, so every chunk is distinct."""
    corpus = os.path.join(HERE, "..", "pcaps")
    text = "\n\n".join(open(os.path.join(corpus, n), encoding="utf-8").read()
                       for n in sorted(os.listdir(corpus)) if n.endswith((".md", ".txt")))
    with open(path, "w", encoding="utf-8") as fh:
        n = 0
        while fh.tell() < megabytes * 1024 * 1024:
            n += 1
            fh.write(f"\n\n# Appendix section {n}\n\n{text}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kills", type=int, default=1, help="leave at 1; see the module docstring")
    ap.add_argument("--megabytes", type=float, default=4)
    args = ap.parse_args()

    r = requests.post(f"{API}/app/auth/register", json={"email": EMAIL, "password": PASSWORD, "password2": PASSWORD})
    if r.status_code != 201:
        r = requests.post(f"{API}/app/auth/login", json={"email": EMAIL, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {r.json()['tokens']['access']}"}
    ws = requests.get(f"{API}/app/auth/workspaces", headers=headers).json()[0]["id"]

    doc = os.path.join(HERE, "results", f"chaos_{int(time.time())}.txt")
    os.makedirs(os.path.dirname(doc), exist_ok=True)
    big_document(doc, args.megabytes)
    log(f"uploading a {os.path.getsize(doc) / 1e6:.1f} MB document")
    with open(doc, "rb") as fh:
        up = requests.post(f"{API}/app/ai/upload-direct", headers=headers,
                           data={"workspace_id": ws}, files={"file": (os.path.basename(doc), fh)})
    os.remove(doc)
    up.raise_for_status()
    file_id = up.json()["file"]["id"]
    log(f"accepted: file #{file_id}, status {up.json()['file']['status']}")

    def status():
        files = requests.get(f"{API}/app/ai/files", params={"workspace_id": ws}, headers=headers).json()["files"]
        return next(f for f in files if f["id"] == file_id)

    kills = 0
    seen = None
    while True:
        f = status()
        if f["status"] != seen:
            log(f"status: {f['status']}" + (f" - {f['error_message']}" if f.get("error_message") else ""))
            seen = f["status"]
        if f["status"] in ("SUCCESS", "FAILED"):
            break
        if f["status"] == "PROCESSING" and kills < args.kills:
            time.sleep(1.5)  # let it get properly into embedding
            pid = busy_child_pid()
            compose("exec", "-T", "worker", "python", "-c", f"import os; os.kill({pid}, 9)")
            kills += 1
            log(f"SIGKILL sent to worker child pid {pid} (kill {kills} of {args.kills})")
            seen = None  # report the status again once the task is redelivered
            time.sleep(2)
        time.sleep(0.5)

    count = compose("exec", "-T", "api", "python", "-c", f"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings'); django.setup()
from app.models import IngestedFile
from Services.Ai_service.embedding import get_qdrant_client, QDRANT_COLLECTION
from qdrant_client.http import models as m
f = IngestedFile.objects.get(id={file_id})
n = get_qdrant_client().count(QDRANT_COLLECTION, count_filter=m.Filter(must=[
    m.FieldCondition(key='metadata.file_id', match=m.MatchValue(value={file_id}))]), exact=True).count
print(f.attempts, f.chunks_stored, n)
""").split()
    attempts, stored, points = map(int, count[-3:])
    log(f"final: {f['status']} after {attempts} deliveries; {stored} chunks recorded, "
        f"{points} vectors in Qdrant ({'no duplicates' if stored == points else 'MISMATCH'})")

    lost = [line for line in compose("logs", "--since", f"{int(time.time() - T0) + 5}s", "worker").splitlines()
            if "WorkerLostError" in line or "exited with" in line or "Gave up" in line or "giving up" in line]
    for line in lost[:8]:
        log("worker log: " + line.split("|", 1)[-1].strip()[:160])
    sys.exit(0 if (f["status"] == "SUCCESS") == (args.kills <= 2) else 1)


if __name__ == "__main__":
    main()
