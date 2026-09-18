import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_INTERNAL_KEY = "change-me-internal-key"


class Settings(BaseSettings):
    # Same shared config file as the API on the native Windows install; see
    # backend/app/config.py.
    model_config = SettingsConfigDict(env_file=os.environ.get("CHRONOS_ENV_FILE", ".env"), extra="ignore")

    api_base_url: str = "http://api:8000/api/v1"
    internal_api_key: str = _INSECURE_INTERNAL_KEY

    # BLUEPRINT.md Section 2.2: default 5 minutes, configurable via env var.
    sync_interval_seconds: int = 300

    # BLUEPRINT.md Section 2.2: default 02:00 local time nightly trigger.
    nightly_hour: int = 2
    nightly_minute: int = 0

    # ASSUMPTION (not specified by BLUEPRINT.md): the K40 device clock is
    # assumed to be set to the pilot location's local time (matches
    # `locations.timezone`'s Phase 1 default, Europe/Tirane — no IANA zone
    # exists for Prishtina; Kosovo and Albania share the same CET/CEST rules,
    # so Europe/Tirane is used). `worker` has no DB access to look up
    # `locations.timezone` per-device, and pyzk returns naive datetimes read
    # directly off the device, so this env var is the single source of truth
    # for localizing device timestamps to UTC before they are pushed to
    # `api`. Must be set correctly per deployment if a device's clock is in a
    # different zone than the location record.
    device_timezone: str = "Europe/Tirane"

    worker_port: int = 8100
    # Native install only: the internal "sync now" endpoint must be reachable
    # from the API on this machine and nothing else. (In Docker, uvicorn's
    # command line binds 0.0.0.0 inside a container that publishes no port.)
    worker_host: str = "127.0.0.1"

    @model_validator(mode="after")
    def _reject_insecure_secret(self) -> "Settings":
        # Same rationale as backend/app/config.py's identical check — the
        # shared secret guards writes into attendance_logs/daily-status, so a
        # process must never silently boot with the placeholder value.
        if os.environ.get("CHECKIN_ALLOW_INSECURE_SECRETS") == "1":
            return self
        if self.internal_api_key == _INSECURE_INTERNAL_KEY:
            raise ValueError(
                "INTERNAL_API_KEY is unset or still the placeholder value — refusing to start. "
                "Set a real random secret (e.g. `openssl rand -hex 32`) in .env."
            )
        return self


settings = Settings()
