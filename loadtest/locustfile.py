"""
Closed-loop load test of the query path: each simulated user sends a question,
waits for the answer, and immediately sends the next. With no think time, N users
means N requests in flight, so throughput at each N shows where the system stops
scaling. See loadtest/README.md for how to run it and what was found.

Setup happens once per run, before any user starts: sign up (or log in), upload
the pcaps/ corpus to the user's workspace, and wait for ingestion to finish.
"""

import json
import os
import random
import time

import requests
from locust import HttpUser, constant, events, task

EMAIL = os.environ.get("LOADTEST_EMAIL", "loadtest@example.com")
PASSWORD = os.environ.get("LOADTEST_PASSWORD", "load-test-Passw0rd!")
CORPUS = os.environ.get("LOADTEST_CORPUS", "/mnt/pcaps")
GOLDEN = os.environ.get("LOADTEST_GOLDEN", "/mnt/evals/golden_set.json")

with open(GOLDEN, encoding="utf-8") as fh:
    # Answerable questions only: an unanswerable one may be refused before the
    # LLM is called, which would make a run look faster than real traffic.
    QUESTIONS = [q["question"] for q in json.load(fh) if q["answerable"]]

STATE = {}


def _auth(host: str) -> str:
    r = requests.post(f"{host}/app/auth/register",
                      json={"email": EMAIL, "password": PASSWORD, "password2": PASSWORD}, timeout=30)
    if r.status_code != 201:
        r = requests.post(f"{host}/app/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    r.raise_for_status()
    return r.json()["tokens"]["access"]


def _seed(host: str, token: str) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = requests.get(f"{host}/app/auth/workspaces", headers=headers, timeout=30).json()[0]["id"]
    # Keys are ws_<id>/<uuid>_<filename>, so a rerun skips files already uploaded.
    have = {f["s3_key"].split("/", 1)[-1].split("_", 1)[-1] for f in requests.get(
        f"{host}/app/ai/files", params={"workspace_id": workspace_id}, headers=headers, timeout=30
    ).json().get("files", [])}
    for name in sorted(os.listdir(CORPUS)):
        if name in have:
            continue
        with open(os.path.join(CORPUS, name), "rb") as fh:
            r = requests.post(f"{host}/app/ai/upload-direct", headers=headers, timeout=60,
                              data={"workspace_id": workspace_id}, files={"file": (name, fh)})
        r.raise_for_status()
    deadline = time.time() + 300
    while time.time() < deadline:
        files = requests.get(f"{host}/app/ai/files", params={"workspace_id": workspace_id},
                             headers=headers, timeout=30).json().get("files", [])
        if files and all(f["status"] in ("SUCCESS", "FAILED") for f in files):
            failed = [f["s3_key"] for f in files if f["status"] == "FAILED"]
            if failed:
                raise RuntimeError(f"ingestion failed for {failed}")
            return workspace_id
        time.sleep(2)
    raise RuntimeError("corpus did not finish ingesting in 5 minutes")


@events.test_start.add_listener
def _setup(environment, **_):
    token = _auth(environment.host)
    STATE["token"] = token
    STATE["workspace_id"] = _seed(environment.host, token)


class QueryUser(HttpUser):
    wait_time = constant(0)

    @task
    def ask(self):
        self.client.post(
            "/app/ai/query",
            json={"question": random.choice(QUESTIONS), "workspace_id": STATE["workspace_id"]},
            headers={"Authorization": f"Bearer {STATE['token']}"},
            name="POST /app/ai/query",
            timeout=180,
        )
