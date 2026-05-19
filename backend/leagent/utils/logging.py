"""Structured logging setup using structlog."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from typing import Literal

import structlog


def setup_logging(
    level: str = "INFO",
    log_format: Literal["json", "console", "auto"] = "auto",
    json_output: bool | None = None,
    log_file: str = "",
) -> None:
    """Configure structlog and stdlib logging for the application.

    Args:
        level: Root log level (DEBUG, INFO, WARNING, ERROR).
        log_format: Output format: "json", "console", or "auto".
            "auto" uses JSON when json_output is True (or when not debug),
            and console otherwise.  Explicit "json"/"console" overrides
            the json_output flag.
        json_output: Legacy flag kept for backwards compatibility.
            Ignored when log_format is not "auto".
        log_file: If non-empty, also write JSON log lines to this file
            (rotating, 10 MB per file, 5 backups).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Resolve the effective format
    if log_format == "json":
        use_json = True
    elif log_format == "console":
        use_json = False
    else:
        # "auto": fall back to the legacy json_output flag
        use_json = json_output if json_output is not None else True

    # --- Renderer -----------------------------------------------------------
    if use_json:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    # --- Processors that run for structlog-originated log calls -------------
    # These run before wrap_for_formatter hands the event dict to the stdlib
    # handler.  They must NOT include TimeStamper / ExcInfo because those run
    # in the formatter's processor chain (shared path for both structlog and
    # foreign stdlib records).
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.ExtraAdder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # --- ProcessorFormatter -------------------------------------------------
    # foreign_pre_chain: runs for stdlib logging.getLogger(__name__) records
    # that did NOT originate from structlog.  Extracts the same metadata so
    # both paths produce identical structured events.
    foreign_pre_chain: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.stdlib.ExtraAdder(),
    ]

    # processors: runs for ALL records (structlog + foreign) after the
    # pre-chain.  Adds timestamp, formats exc_info, decodes bytes.
    fmt_processors: list[structlog.types.Processor] = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if use_json:
        fmt_processors.append(structlog.processors.format_exc_info)
    fmt_processors += [
        structlog.processors.UnicodeDecoder(),
        renderer,
    ]
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=foreign_pre_chain,
        processors=fmt_processors,
    )

    # --- Root stdlib logger -------------------------------------------------
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)
    root_logger.setLevel(log_level)

    # --- Optional rotating file handler (always JSON) -----------------------
    if log_file:
        file_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=foreign_pre_chain,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ],
        )
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # --- Third-party logger tuning ------------------------------------------
    for noisy in (
        "uvicorn.access",
        "httpcore",
        "httpx",
        "asyncio",
        "pymilvus",
        "hpack",
        "aiohttp",
        "multipart",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("uvicorn.error").setLevel(log_level)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.WARNING if log_level > logging.DEBUG else logging.INFO
    )
