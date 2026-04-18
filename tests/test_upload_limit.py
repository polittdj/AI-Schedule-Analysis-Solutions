"""Regression tests for the 500 MB upload limit.

Ratifies BUILD-PLAN.md §2.11 and Milestone 1 Acceptance Criterion 3:

- ``MAX_CONTENT_LENGTH`` is exactly 500 * 1024 * 1024 bytes.
- A POST whose ``Content-Length`` header exceeds the limit returns
  HTTP 413, *without* the client having to transmit the full body —
  Flask rejects on the advertised length before reading the payload.
- The 413 response body is structured JSON with an ``error`` field.
"""

from __future__ import annotations

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app
from app.config import UPLOAD_LIMIT_BYTES


@pytest.fixture(scope="module")
def upload_app() -> Flask:
    """App with a test-only /upload echo route for exercising 413 handling."""
    app = create_app()
    app.config.update(TESTING=True)

    @app.post("/upload")
    def _echo() -> tuple[dict[str, int], int]:  # pragma: no cover — 413 short-circuits
        from flask import request

        body = request.get_data() or b""
        return {"received_bytes": len(body)}, 200

    return app


@pytest.fixture()
def upload_client(upload_app: Flask) -> FlaskClient:
    return upload_app.test_client()


def test_max_content_length_is_exactly_500_mib() -> None:
    app = create_app()
    assert UPLOAD_LIMIT_BYTES == 500 * 1024 * 1024
    assert app.config["MAX_CONTENT_LENGTH"] == 500 * 1024 * 1024


def _post_with_content_length(client: FlaskClient, length: int):  # noqa: ANN202
    # Returns a TestResponse; no annotation to avoid importing the
    # internal Werkzeug test response type here.
    """POST an empty body while advertising a specific Content-Length.

    Flask checks ``request.content_length`` against ``MAX_CONTENT_LENGTH``
    from the WSGI ``CONTENT_LENGTH`` environ, so we overwrite that
    directly rather than transmitting a >500 MB payload.
    """
    return client.post(
        "/upload",
        data=b"",
        environ_overrides={"CONTENT_LENGTH": str(length)},
    )


def test_oversized_upload_rejected_with_413(upload_client: FlaskClient) -> None:
    response = _post_with_content_length(upload_client, UPLOAD_LIMIT_BYTES + 1)
    assert response.status_code == 413


def test_413_response_body_is_structured_json(upload_client: FlaskClient) -> None:
    response = _post_with_content_length(upload_client, UPLOAD_LIMIT_BYTES + 1)
    assert response.status_code == 413
    assert response.is_json
    payload = response.get_json()
    assert payload is not None
    assert payload["error"] == "upload_too_large"
    assert payload["limit_bytes"] == UPLOAD_LIMIT_BYTES


def test_within_limit_upload_is_accepted(upload_client: FlaskClient) -> None:
    response = upload_client.post("/upload", data=b"small-payload")
    assert response.status_code == 200
