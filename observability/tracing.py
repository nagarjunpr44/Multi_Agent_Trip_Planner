from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def configure_tracing() -> None:
    """
    Configure LangSmith tracing if LANGCHAIN_TRACING_V2=true and
    LANGCHAIN_API_KEY is set.  Safe no-op if langsmith is not installed.
    """
    tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    api_key = os.getenv("LANGCHAIN_API_KEY", "")

    if not tracing_enabled:
        logger.debug("LangSmith tracing disabled (LANGCHAIN_TRACING_V2 not set)")
        return

    if not api_key:
        logger.warning(
            "LANGCHAIN_TRACING_V2=true but LANGCHAIN_API_KEY is missing — tracing skipped"
        )
        return

    try:
        import langsmith  # noqa: F401 — triggers automatic LangChain tracing
        project = os.getenv("LANGCHAIN_PROJECT", "AgenticTripPlanner")
        logger.info("LangSmith tracing enabled for project '%s'", project)
    except ImportError:
        logger.warning("langsmith package not installed — tracing disabled")
