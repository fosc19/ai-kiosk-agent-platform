"""Main entry point for MCP Tools server."""

import asyncio
import logging
import sys

import structlog

from mcp_tools.config import settings


def configure_logging():
    """Configure structured logging."""
    processors = [
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
    ]

    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level, logging.INFO)
        ),
    )


def main():
    """Main entry point."""
    configure_logging()
    log = structlog.get_logger()

    # Determine database type for logging
    db_display = settings.database_url
    if "@" in db_display:
        db_display = db_display.split("@")[-1]  # Hide credentials for PostgreSQL

    log.info(
        "mcp_tools_starting",
        transport=settings.transport,
        database_url=db_display,
    )

    # Initialize database (creates tables for SQLite, runs seeds)
    try:
        from mcp_tools.db.session import init_db_and_seed
        init_db_and_seed()
        log.info("database_initialized")
    except Exception as e:
        log.warning("database_init_warning", error=str(e))

    try:
        if settings.transport == "http":
            from mcp_tools.http_server import run_http_server
            run_http_server()
        else:
            from mcp_tools.server import run_server
            asyncio.run(run_server())
    except KeyboardInterrupt:
        log.info("mcp_tools_shutdown")
        sys.exit(0)
    except Exception as e:
        log.error("mcp_tools_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
