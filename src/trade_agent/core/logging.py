"""Process logging. Formatters must never emit secrets."""

from __future__ import annotations

import logging
import re
import sys

# Common secret-shaped tokens. Applied as a last-resort redaction on log records.
_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|token|authorization)\s*[:=]\s*([^\s,;]+)"
)


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _redact(str(v)) for k, v in record.args.items()}
            else:
                record.args = tuple(_redact(str(a)) for a in record.args)
        return True


def _redact(text: str) -> str:
    return _SECRET_RE.sub(r"\1=***", text)


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure the ``trade_agent`` logger once and return it."""
    logger = logging.getLogger("trade_agent")
    if logger.handlers:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)sZ %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    handler.addFilter(_RedactFilter())
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under ``trade_agent``."""
    if name.startswith("trade_agent"):
        return logging.getLogger(name)
    return logging.getLogger(f"trade_agent.{name}")
