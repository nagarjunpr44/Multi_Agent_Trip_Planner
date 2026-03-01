"""
AgenticTripPlanner — application entrypoint.

Usage:
  python main.py                  # Start API server (default)
  python main.py --ui             # Start Streamlit UI
  python main.py --migrate        # Run Alembic migrations then exit
"""
from __future__ import annotations

import argparse
import os
import sys

# Ensure project root is on sys.path when running directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from observability.logging import configure_logging
from observability.tracing import configure_tracing


def run_api() -> None:
    import uvicorn
    from api.app import create_app

    configure_logging()
    configure_tracing()

    app = create_app()

    # Mount Prometheus metrics endpoint if available
    try:
        from observability.metrics import mount_metrics_endpoint
        mount_metrics_endpoint(app)
    except Exception:
        pass

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        access_log=True,
    )


def run_ui() -> None:
    import subprocess

    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run", "ui/app.py",
            "--server.address", os.getenv("UI_HOST", "0.0.0.0"),
            "--server.port", os.getenv("UI_PORT", "8501"),
        ],
        check=True,
    )


def run_migrate() -> None:
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
    )
    sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="AgenticTripPlanner")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--ui", action="store_true", help="Start Streamlit UI")
    group.add_argument("--migrate", action="store_true", help="Run DB migrations")
    args = parser.parse_args()

    if args.ui:
        run_ui()
    elif args.migrate:
        run_migrate()
    else:
        run_api()


if __name__ == "__main__":
    main()
