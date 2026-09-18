"""chronos-worker — native (non-Docker) entry point.

Compiled with Nuitka into chronos-worker.exe for the Windows install. Runs the
same app the Docker `worker` container runs: the device-polling scheduler plus
the small internal HTTP endpoint the API calls for "Sync now".

That endpoint only ever needs to be reachable from the API on this same
machine, so natively it listens on 127.0.0.1 — in Docker the container simply
publishes no port. Configuration comes from CHRONOS_ENV_FILE, like the server.
"""
import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chronos-worker", description="Run the chronos device-sync worker.")
    parser.add_argument("--host", help="interface for the internal endpoint (default: WORKER_HOST, 127.0.0.1)")
    parser.add_argument("--port", type=int, help="port for the internal endpoint (default: WORKER_PORT, 8100)")
    args = parser.parse_args(argv)

    import uvicorn

    from worker.config import settings
    from worker.main import app

    uvicorn.run(
        app,
        host=args.host or settings.worker_host,
        port=args.port or settings.worker_port,
        loop="asyncio",
        http="h11",
        ws="none",
        proxy_headers=False,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
