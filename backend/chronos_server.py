"""chronos-server — native (non-Docker) entry point.

Compiled with Nuitka into chronos-server.exe for the Windows install, and
runnable from source (`python chronos_server.py`) for development. It does
what the Docker `api` container's command line does — run database migrations,
then serve — plus the two jobs nginx does in Docker:

  * serve the built web UI (FRONTEND_DIST, defaulting to ./web next to this
    program), with single-page-app fallback;
  * keep /api/v1/internal/ reachable only from this machine.

Configuration comes from the file named by CHRONOS_ENV_FILE (the Windows
service sets it to C:\\ProgramData\\Chronos\\chronos.env), falling back to
.env in the working directory.
"""
import argparse
import os
import sys
from pathlib import Path


def _home() -> Path:
    """Directory this program lives in, compiled or not.

    A Nuitka standalone build puts data files (alembic/, web/) next to the
    executable, so for the compiled program that is argv[0]'s folder; from
    source it is this file's folder. CHRONOS_HOME overrides both.
    """
    override = os.environ.get("CHRONOS_HOME")
    if override:
        return Path(override).resolve()
    if "__compiled__" in globals():
        return Path(sys.argv[0]).resolve().parent
    return Path(__file__).resolve().parent


def _run_migrations(home: Path) -> None:
    """`alembic upgrade head`, without needing alembic.ini on disk.

    The migration scripts are loaded from home/alembic at run time — that is
    how alembic works — so they ship as files beside the executable. They
    contain only schema DDL, which the database itself exposes anyway; none of
    the payroll or attendance logic lives in them.
    """
    from alembic import command
    from alembic.config import Config

    script_location = home / "alembic"
    if not (script_location / "env.py").is_file():
        raise RuntimeError(f"migrations not found at {script_location}")
    cfg = Config()
    cfg.set_main_option("script_location", str(script_location))
    command.upgrade(cfg, "head")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chronos-server", description="Run the chronos API and web UI.")
    parser.add_argument("--host", help="interface to listen on (default: SERVER_HOST setting, 0.0.0.0)")
    parser.add_argument("--port", type=int, help="port to listen on (default: SERVER_PORT setting, 8080)")
    parser.add_argument("--migrate-only", action="store_true", help="apply database migrations and exit")
    parser.add_argument("--skip-migrations", action="store_true", help="start without migrating (diagnostics only)")
    args = parser.parse_args(argv)

    home = _home()

    # Native mode has no nginx in front of it, so it takes on nginx's two
    # jobs. Set before app.config is imported, because Settings reads the
    # environment once at import. An explicit environment variable still
    # wins, for diagnostics; a value in the env file does not, on purpose —
    # the internal endpoints must never be opened to the network by an edit
    # to a config file.
    os.environ["INTERNAL_LOOPBACK_ONLY"] = os.environ.get("INTERNAL_LOOPBACK_ONLY", "true")
    web = home / "web"
    if "FRONTEND_DIST" not in os.environ and (web / "index.html").is_file():
        os.environ["FRONTEND_DIST"] = str(web)

    from app.config import settings

    if not args.skip_migrations:
        _run_migrations(home)
    if args.migrate_only:
        return 0

    import uvicorn

    from app.main import app

    uvicorn.run(
        app,
        host=args.host or settings.server_host,
        port=args.port or settings.server_port,
        # Pinned rather than auto-detected: auto-detection imports optional
        # accelerators by name at run time, which a compiled build may not
        # contain. Both of these are pure Python and always present.
        loop="asyncio",
        http="h11",
        # Nothing sits in front of this server, so X-Forwarded-For must not be
        # trusted — it is what the internal-endpoint loopback check relies on.
        proxy_headers=False,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
