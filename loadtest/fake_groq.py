"""
A stand-in for Groq's OpenAI-compatible chat API, for load testing only.

Why not load-test against Groq itself: on the free tier the limit is 8,000 tokens
per minute, and one agentic query uses ~3,300, so Groq caps the whole system at
about 2 queries a minute. A load test against it measures Groq's quota, not this
system. This server answers in the same shape, after a delay drawn from the range
measured against the real API (0.70-0.96 s per call, median 0.76 s, 1,271-token
prompt; see loadtest/README.md), so what remains is the cost of this system's own
code: request handling, embedding, Qdrant, Postgres and the worker model.

The app is not modified. GROQ_API_BASE points the client here, which is the only
difference from production.

    python fake_groq.py            # listens on :8080
"""

import json
import os
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MIN_S = float(os.environ.get("FAKE_LLM_MIN_SECONDS", "0.70"))
MAX_S = float(os.environ.get("FAKE_LLM_MAX_SECONDS", "0.96"))


def _reply(messages: list[dict]) -> str:
    """The JSON each of the agent's prompts expects, chosen by its system prompt."""
    system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
    user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    if "sub_queries" in system:
        return json.dumps({"sub_queries": [user.removeprefix("Question: ").strip()]})
    if "verdict" in system:
        return json.dumps({"verdict": "PASS", "unsupported_claims": []})
    return json.dumps({
        "answer": "Stub answer from the load-test LLM.",
        "citations": [],
        "unverified": "",
        "confidence_score": 0.9,
    })


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive, as the real API allows

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        messages = body.get("messages", [])
        time.sleep(random.uniform(MIN_S, MAX_S))
        content = _reply(messages)
        prompt_tokens = sum(len(str(m.get("content", ""))) for m in messages) // 4
        completion_tokens = len(content) // 4
        payload = json.dumps({
            "id": "chatcmpl-loadtest",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "stub"),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # one line per call would drown the test output
        pass


if __name__ == "__main__":
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
