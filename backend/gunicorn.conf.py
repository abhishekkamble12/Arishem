"""
Gunicorn hooks. Bind address, worker count and timeouts stay on the command line
(Dockerfile, docker-compose.prod.yml), which overrides anything set here.
"""


def post_worker_init(worker):
    """
    Runs in each worker after it has loaded the app and before it serves a request,
    so the embedding model and LLM client are ready before the first query rather
    than loaded during it. See Services/warmup.py for the measurements.
    """
    from Services.warmup import warm_up

    worker.log.info("Worker %s warmed up in %.1fs", worker.pid, warm_up())
