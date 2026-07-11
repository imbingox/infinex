import json
import logging

from infinex.control_plane.logging import JsonFormatter


def test_json_formatter_includes_request_context() -> None:
    record = logging.LogRecord(
        name="infinex.control_plane.http",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="http_request",
        args=(),
        exc_info=None,
    )
    record.request_id = "request-1"
    record.method = "GET"
    record.path = "/api/health"
    record.status_code = 200
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "http_request"
    assert payload["request_id"] == "request-1"
    assert payload["status_code"] == 200
