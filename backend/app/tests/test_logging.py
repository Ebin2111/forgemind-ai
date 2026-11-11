"""Logging: redaction, formats, request IDs and safe reconfiguration."""
import json
import logging

import pytest

from backend.app.core.logging import (
    JsonFormatter,
    RedactingFormatter,
    TEXT_FORMAT,
    configure_logging,
    redact,
    request_id_ctx,
)


@pytest.fixture
def restore_logging():
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers, root.level = handlers, level


def _record(msg="hello", *args, **kw):
    return logging.LogRecord("forgemind.test", logging.INFO, __file__, 1, msg, args, None, **kw)


class TestRedact:
    @pytest.mark.parametrize(
        "raw, secret",
        [
            ("calling with AIzaSyA1234567890abcdefghijklmnop", "AIzaSyA1234567890abcdefghijklmnop"),
            ("Authorization: Bearer abc.def-123456789", "abc.def-123456789"),
            ("GET /v1?key=supersecret123&x=1", "supersecret123"),
            ("api_key: hunter2hunter2", "hunter2hunter2"),
            ("postgresql://app:p4ssw0rd@db:5432/x", "p4ssw0rd"),
        ],
    )
    def test_secrets_are_masked(self, raw, secret):
        out = redact(raw)
        assert secret not in out and "[REDACTED]" in out

    def test_ordinary_text_is_untouched(self):
        s = "GET /api/equipment -> 200 (4 ms) sqlite:////app/data/forgemind.db"
        assert redact(s) == s


class TestFormatters:
    def test_text_format_has_request_id_and_redacts(self):
        from backend.app.core.logging import RequestIdFilter

        rec = _record("token=abc123456")
        token = request_id_ctx.set("req-1")
        try:
            RequestIdFilter().filter(rec)
        finally:
            request_id_ctx.reset(token)
        line = RedactingFormatter(TEXT_FORMAT).format(rec)
        assert "[req-1]" in line and "abc123456" not in line

    def test_json_is_valid_and_complete(self):
        rec = _record("done %s", "ok")
        rec.request_id = "r9"
        rec.duration_ms = 12
        data = json.loads(JsonFormatter().format(rec))
        assert data["message"] == "done ok" and data["request_id"] == "r9"
        assert data["level"] == "INFO" and data["duration_ms"] == 12
        assert data["timestamp"].endswith("+00:00")

    def test_json_includes_and_redacts_exceptions(self):
        try:
            raise RuntimeError("failed with key=topsecret99")
        except RuntimeError:
            import sys

            rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "boom", (), sys.exc_info())
        data = json.loads(JsonFormatter().format(rec))
        assert "RuntimeError" in data["exception"] and "topsecret99" not in data["exception"]

    def test_json_survives_unserialisable_extra(self):
        rec = _record()
        rec.thing = object()
        assert "thing" in json.loads(JsonFormatter().format(rec))


class TestConfigure:
    def test_is_idempotent_and_sets_level(self, restore_logging):
        configure_logging("DEBUG")
        configure_logging("WARNING")
        root = logging.getLogger()
        assert len(root.handlers) == 1 and root.level == logging.WARNING

    def test_json_format_selected(self, restore_logging):
        configure_logging("INFO", "json")
        assert isinstance(logging.getLogger().handlers[0].formatter, JsonFormatter)

    @pytest.mark.parametrize("level, fmt", [("LOUD", "text"), ("INFO", "xml")])
    def test_invalid_values_rejected(self, level, fmt):
        with pytest.raises(ValueError):
            configure_logging(level, fmt)

    def test_noisy_libraries_quieted_unless_debug(self, restore_logging):
        configure_logging("INFO")
        assert logging.getLogger("httpx").level == logging.WARNING
        configure_logging("DEBUG")
        assert logging.getLogger("httpx").level == logging.DEBUG

    def test_end_to_end_output_is_redacted(self, restore_logging, capsys):
        configure_logging("INFO", "json")
        token = request_id_ctx.set("abc")
        try:
            logging.getLogger("forgemind").info("url https://x/y?key=leakme12345")
        finally:
            request_id_ctx.reset(token)
        out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert out["request_id"] == "abc" and "leakme12345" not in out["message"]

    def test_settings_accept_log_format_case_insensitively(self, monkeypatch):
        from backend.app.core.config import Settings

        monkeypatch.setenv("LOG_FORMAT", "JSON")
        assert Settings().log_format == "json"