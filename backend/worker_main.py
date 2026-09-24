"""Standalone worker process for background jobs.

Runs the background workers (action runs) in a dedicated container instead of
uvicorn. No FastAPI, no HTTP server.

The full service graph is built by the SAME `_setup_generic_modules` builder the
web app uses (`main.py`), so wiring can never drift between web and worker. The
only difference is that this process passes `app_router=None` (no HTTP
controllers) and enables the worker threads via configuration:

  - background_jobs_configuration.worker_enabled  (ACTION_RUNS_WORKER_ENABLED)

Every other manager's start() is a no-op flag set, so starting the whole graph
here only launches the gated worker thread(s).
"""

from __future__ import annotations

import os

# Must be set before importing main: it tells main.py NOT to build the web
# ASGI app at import time (the worker builds its own graph below).
os.environ.setdefault("WORKER_MODE", "true")

import signal  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402

import main as app_main  # noqa: E402
from bootstrap.runner import run_bootstrap  # noqa: E402
from common.configuration import Configuration  # noqa: E402
from common.logger import logger  # noqa: E402
from database.manager import DatabaseServiceManager  # noqa: E402

_shutdown = threading.Event()
_managed_services: list = []


def _build_worker_services() -> list:
    config = Configuration()
    database_service_manager = DatabaseServiceManager(config)

    if os.environ.get("WORKER_SKIP_MIGRATIONS", "false").lower() != "true":
        try:
            run_bootstrap(database_service_manager, config)
        except Exception as exc:
            logger.warning("Worker bootstrap (migrations) failed: %s", exc)

    # Shared service-graph builder — same wiring as the web app, no HTTP router.
    return app_main._setup_generic_modules(None, database_service_manager, config)


def _handle_shutdown(signum: int, frame: object) -> None:
    logger.info("Worker received shutdown signal %d — stopping", signum)
    for manager in _managed_services:
        stop = getattr(manager, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception as exc:
                logger.debug("stop() failed for %s: %s", type(manager).__name__, exc)
    _shutdown.set()
    sys.exit(0)


def main() -> None:
    global _managed_services  # noqa: PLW0603

    logger.info("Starting background jobs worker")
    _managed_services = _build_worker_services()

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    for manager in _managed_services:
        start = getattr(manager, "start", None)
        if callable(start):
            start()

    logger.info("Worker started — action runs worker running")
    _shutdown.wait()


if __name__ == "__main__":
    main()
