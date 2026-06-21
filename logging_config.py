"""Structured logging setup for the Internal Agent Service.

Provides:
- A human-readable console logger for general app events.
- A machine-readable JSONL logger (one JSON object per line) for LLM
  request/response interactions, with size-based rotation.
- A `request_id` ContextVar so logs from the same HTTP request can be
  correlated across modules.
"""

import json
import logging
import os
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

# ---------------------------------------------------------------------------
# Configuration (override via environment variables)
# ---------------------------------------------------------------------------

LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
# Max bytes per rotated file and how many backups to keep.
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))  # 10 MB
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))

os.makedirs(LOG_DIR, exist_ok=True)

# Correlation id shared across a single request lifecycle.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id() -> str:
    """Generate and bind a fresh request id to the current context."""
    rid = uuid.uuid4().hex
    request_id_ctx.set(rid)
    return rid


def current_request_id() -> str:
    return request_id_ctx.get()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    """Render each log record as a single-line JSON object.

    Any structured payload passed via `extra={"payload": {...}}` is merged
    into the top-level object so LLM interaction fields are queryable.
    """

    def format(self, record: logging.LogRecord) -> str:
        base = {
            "timestamp": _utc_now_iso(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", current_request_id()),
            "message": record.getMessage(),
        }

        payload = getattr(record, "payload", None)
        if isinstance(payload, dict):
            base.update(payload)

        if record.exc_info:
            base["exception"] = self.formatException(record.exc_info)

        return json.dumps(base, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """Compact, human-readable console output that includes the request id."""

    def format(self, record: logging.LogRecord) -> str:
        rid = getattr(record, "request_id", current_request_id())
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"{ts} | {record.levelname:<7} | {rid[:8]} | {record.name} | {record.getMessage()}"

        # Surface explicit error fields (error_type/error) carried in the payload.
        payload = getattr(record, "payload", None)
        if isinstance(payload, dict) and payload.get("error"):
            err_type = payload.get("error_type", "Error")
            line += f"\n    └─ {err_type}: {payload['error']}"

        # Append the full traceback when an exception is attached.
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)

        return line


class _RequestIdFilter(logging.Filter):
    """Inject the current request id into every record that lacks one."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = current_request_id()
        return True


# ---------------------------------------------------------------------------
# Logger factory
# ---------------------------------------------------------------------------

_request_id_filter = _RequestIdFilter()


def _build_rotating_handler(filename: str, formatter: logging.Formatter) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        os.path.join(LOG_DIR, filename),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    handler.addFilter(_request_id_filter)
    return handler


def _configure() -> tuple[logging.Logger, logging.Logger]:
    # General application logger -> console + app.log (human readable)
    app_logger = logging.getLogger("agent.app")
    app_logger.setLevel(LOG_LEVEL)
    app_logger.propagate = False

    if not app_logger.handlers:
        console = logging.StreamHandler()
        console.setFormatter(ConsoleFormatter())
        console.addFilter(_request_id_filter)
        app_logger.addHandler(console)

        app_file = _build_rotating_handler("app.log", JsonFormatter())
        app_logger.addHandler(app_file)

    # Dedicated LLM interaction logger -> llm.jsonl (structured only)
    llm_logger = logging.getLogger("agent.llm")
    llm_logger.setLevel(LOG_LEVEL)
    llm_logger.propagate = False

    if not llm_logger.handlers:
        llm_file = _build_rotating_handler("llm.jsonl", JsonFormatter())
        llm_logger.addHandler(llm_file)
        # Also surface a concise line on the console for visibility.
        console = logging.StreamHandler()
        console.setFormatter(ConsoleFormatter())
        console.addFilter(_request_id_filter)
        llm_logger.addHandler(console)

    return app_logger, llm_logger


app_logger, llm_logger = _configure()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _preview(text, limit: int = 500):
    """Return a length-limited preview for console-friendly fields."""
    if text is None:
        return None
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated {len(text) - limit} chars]"


def log_llm_request(*, agent_name: str, model: str, system_prompt: str,
                    user_message: str) -> None:
    """Log an outgoing LLM request."""
    llm_logger.info(
        "llm_request agent=%s model=%s",
        agent_name,
        model,
        extra={"payload": {
            "event": "llm_request",
            "agent_name": agent_name,
            "model": model,
            "system_prompt": system_prompt,
            "user_message": user_message,
            "user_message_chars": len(user_message or ""),
        }},
    )


def log_llm_response(*, agent_name: str, model: str, response_text: str,
                     latency_ms: float, usage: dict | None = None) -> None:
    """Log a successful LLM response with timing and token usage."""
    payload = {
        "event": "llm_response",
        "agent_name": agent_name,
        "model": model,
        "response": response_text,
        "response_chars": len(response_text or ""),
        "latency_ms": round(latency_ms, 2),
    }
    if usage:
        payload["usage"] = usage

    llm_logger.info(
        "llm_response agent=%s model=%s latency=%.0fms resp=%r",
        agent_name,
        model,
        latency_ms,
        _preview(response_text, 120),
        extra={"payload": payload},
    )


def log_llm_error(*, agent_name: str, model: str, latency_ms: float,
                  error: Exception) -> None:
    """Log a failed LLM call."""
    llm_logger.error(
        "llm_error agent=%s model=%s latency=%.0fms error=%s",
        agent_name,
        model,
        latency_ms,
        error,
        extra={"payload": {
            "event": "llm_error",
            "agent_name": agent_name,
            "model": model,
            "latency_ms": round(latency_ms, 2),
            "error_type": type(error).__name__,
            "error": str(error),
        }},
        exc_info=True,
    )
