"""Application logging: one handler, per-request correlation IDs, secret redaction.

Two output formats, chosen with ``LOG_FORMAT``:

* ``text`` (default) - readable single lines for local development.
* ``json``           - one JSON object per line for log collectors (Loki, CloudWatch, ELK).

Every line carries the ``request_id`` of the request being served, so all messages for one call can be
found together; the same ID is returned to the client in the ``X-Request-ID`` header.
Secrets (API keys, bearer tokens, URL passwords) are masked in the final output whatever the code logged,
including exception tracebacks.
"""
import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

TEXT_FORMAT = "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"

# Libraries that are chatty at INFO/DEBUG and add no value to an operator.
_QUIET_LOGGERS = ("httpx", "httpcore", "urllib3", "google_genai", "google.auth", "filelock", "PIL")

# Attributes every LogRecord has; anything else was passed through ``extra=`` and is kept in JSON output.
_RESERVED = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime", "request_id", "taskName"}

# ---- redaction ----------------------------------------------------------------------------
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), "[REDACTED]"),  # Google API keys
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{8,}"), r"\1 [REDACTED]"),
    (re.compile(r"(?i)\b(api[_-]?key|key|token|secret|password|passwd)(\s*[=:]\s*)[^\s&'\",}]+"), r"\1\2[REDACTED]"),
    (re.compile(r"(?i)(\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:)[^@\s/]+(@)"), r"\1[REDACTED]\2"),  # scheme://user:pw@host
)


def redact(text: str) -> str:
    """Mask credentials in ``text``. Safe to call on any string."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


# ---- filter and formatters ----------------------------------------------------------------
class RequestIdFilter(logging.Filter):
    """Stamp every record with the current request's ID ('-' outside a request)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class RedactingFormatter(logging.Formatter):
    """Readable line format; masks secrets in the message and in tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Extra fields passed via ``extra={...}`` are included."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        if record.stack_info:
            payload["stack"] = redact(self.formatStack(record.stack_info))
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = redact(value) if isinstance(value, str) else value
        # Redact each value BEFORE serialising: masking the finished JSON text could eat an escaping
        # backslash and produce invalid JSON. default=str: a non-serialisable extra must never break logging.
        return json.dumps(payload, ensure_ascii=False, default=str)


# ---- setup --------------------------------------------------------------------------------
def configure_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Install the single stdout handler. Safe to call repeatedly (replaces, never stacks, handlers)."""
    level = str(level).upper()
    if level not in logging.getLevelNamesMapping():
        raise ValueError(f"Unknown log level: {level!r}")
    if fmt not in ("text", "json"):
        raise ValueError(f"Unknown log format: {fmt!r} (use 'text' or 'json')")

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(JsonFormatter() if fmt == "json" else RedactingFormatter(TEXT_FORMAT))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # uvicorn: route its own messages through our handler; our middleware writes the request line instead
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    logging.getLogger("uvicorn.access").disabled = True

    # Quiet libraries stay at WARNING unless the operator asked for DEBUG.
    quiet = logging.DEBUG if level == "DEBUG" else logging.WARNING
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(quiet)