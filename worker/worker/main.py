import hmac
import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import Depends, FastAPI, Header, HTTPException, status

from worker import api_client
from worker.config import settings
from worker.sync import sync_all_devices, sync_one_device

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker.main")

scheduler = BackgroundScheduler()


def _scheduled_sync():
    logger.info("Running scheduled device sync")
    results = sync_all_devices()
    logger.info("Sync results: %s", results)


def _scheduled_nightly_process():
    # Processes "yesterday" — the nightly job runs after midnight for the
    # day that just ended, per BLUEPRINT.md Section 2.2/5.4.
    work_date = date.today() - timedelta(days=1)
    logger.info("Running nightly daily-status processing for %s", work_date)
    result = api_client.process_daily_status(work_date)
    logger.info("Nightly processing result: %s", result)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        _scheduled_sync,
        trigger=IntervalTrigger(seconds=settings.sync_interval_seconds),
        id="device_sync",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _scheduled_nightly_process,
        trigger=CronTrigger(hour=settings.nightly_hour, minute=settings.nightly_minute),
        id="nightly_process",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "Worker scheduler started: sync every %ss, nightly processing at %02d:%02d",
        settings.sync_interval_seconds,
        settings.nightly_hour,
        settings.nightly_minute,
    )
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="chronos sync worker", lifespan=lifespan)


def verify_internal_key(x_internal_key: str = Header(default="")) -> None:
    # hmac.compare_digest avoids a timing side-channel on the shared secret
    # comparison (see backend/app/deps.py's identical fix).
    if not x_internal_key or not hmac.compare_digest(x_internal_key, settings.internal_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal API key")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/sync/{device_id}", dependencies=[Depends(verify_internal_key)])
def manual_sync(device_id: int):
    """Manual on-demand sync trigger — called by `api`'s
    `POST /devices/{id}/sync` (BLUEPRINT.md Section 4.3), authenticated with
    the same shared X-Internal-Key used for worker->api calls."""
    devices = api_client.get_active_devices()
    device = next((d for d in devices if d["id"] == device_id), None)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found or inactive")
    return sync_one_device(device)
