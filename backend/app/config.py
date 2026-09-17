from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel default values. These exist only so the app can import/start for
# tooling purposes (e.g. `alembic` autogenerate) without a .env file; they
# must never be used for an actual running deployment. SECURITY: enforced by
# the validator below — see BACKEND_NOTES.md / SECURITY_REPORT.md ("insecure
# default secrets") for why docker-compose.yml's `${VAR:?...}` requirement
# alone was not sufficient defense-in-depth (it doesn't cover non-Compose
# deployments, e.g. bare `uvicorn` with a missing/incomplete .env).
_INSECURE_JWT_SECRET = "change-me-in-production"
_INSECURE_INTERNAL_KEY = "change-me-internal-key"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "checkin"
    postgres_user: str = "checkin"
    postgres_password: str = "checkin"

    jwt_secret: str = _INSECURE_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 8

    internal_api_key: str = _INSECURE_INTERNAL_KEY
    worker_internal_url: str = "http://worker:8100"

    # Comma-separated list. Defaults cover the Vite dev server for local
    # development; the CLAUDE.md/BLUEPRINT.md production topology serves
    # frontend and api same-origin via nginx proxy, so CORS is not exercised
    # in that path, but is needed for `npm run dev` against a local `api`.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # LAN-only, no-TLS Phase 1 (BLUEPRINT.md Section 6.1/8) — kept False by
    # default to match the documented Phase 1 deployment. Set COOKIE_SECURE=true
    # once the deployment is served over HTTPS (required before any Phase 2
    # internet-facing exposure, per BLUEPRINT.md Section 6.1's own flag).
    cookie_secure: bool = False

    @model_validator(mode="after")
    def _reject_insecure_secrets(self) -> "Settings":
        import os

        # Explicit, opt-in escape hatch only for tooling that imports this
        # module without serving traffic (e.g. an isolated `alembic` check).
        # Never set this in any real deployment.
        if os.environ.get("CHECKIN_ALLOW_INSECURE_SECRETS") == "1":
            return self
        if self.jwt_secret == _INSECURE_JWT_SECRET:
            raise ValueError(
                "JWT_SECRET is unset or still the placeholder value — refusing to start. "
                "Set a real random secret (e.g. `openssl rand -hex 32`) in .env."
            )
        if self.internal_api_key == _INSECURE_INTERNAL_KEY:
            raise ValueError(
                "INTERNAL_API_KEY is unset or still the placeholder value — refusing to start. "
                "Set a real random secret (e.g. `openssl rand -hex 32`) in .env."
            )
        return self

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
