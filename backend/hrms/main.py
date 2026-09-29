import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hrms.api.v1.routes import (
    allocations,
    assets,
    auth,
    employees,
    helpdesk,
    hr_cockpit,
    onboarding,
    performance,
    project_approvals,
    projects,
    public_content,
    roles,
    timesheets,
    work,
)
from hrms.config import get_settings
from hrms.workflows.platform import install_workflow_checks

settings = get_settings()
install_workflow_checks()
logger = logging.getLogger("hrms")


async def _outbox_loop() -> None:
    """Drains the notification outbox (and expires stale invitations) forever.
    Failures are logged and retried on the next tick — never crashes the app."""
    from hrms.database import AsyncSessionLocal
    from hrms.services import notification_service, onboarding_service

    tick = 0
    while True:
        await asyncio.sleep(settings.OUTBOX_FLUSH_INTERVAL_SECONDS)
        tick += 1
        try:
            async with AsyncSessionLocal() as db:
                await notification_service.drain_outbox(db)
                # Retry failed sends + expire invitations occasionally (~10 min).
                if tick % 30 == 0:
                    await notification_service.retry_failed(db)
                    await onboarding_service.flag_expired_invitations(db)
        except Exception:  # noqa: BLE001
            logger.exception("Outbox drain tick failed; will retry")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_outbox_loop())
    yield
    task.cancel()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(roles.router, prefix=API_PREFIX)
app.include_router(employees.router, prefix=API_PREFIX)
app.include_router(projects.router, prefix=API_PREFIX)
app.include_router(project_approvals.router, prefix=API_PREFIX)
app.include_router(allocations.router, prefix=API_PREFIX)
app.include_router(timesheets.router, prefix=API_PREFIX)
app.include_router(assets.router, prefix=API_PREFIX)
app.include_router(helpdesk.router, prefix=API_PREFIX)
app.include_router(onboarding.router, prefix=API_PREFIX)
app.include_router(performance.router, prefix=API_PREFIX)
app.include_router(work.router, prefix=API_PREFIX)
app.include_router(hr_cockpit.router, prefix=API_PREFIX)
app.include_router(public_content.router, prefix=API_PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.ENV}
