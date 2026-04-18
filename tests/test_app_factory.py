"""Smoke tests for the Flask application factory."""

from __future__ import annotations

from flask import Flask
from flask.testing import FlaskClient

from app import create_app


def test_create_app_returns_flask_instance() -> None:
    app = create_app()
    assert isinstance(app, Flask)


def test_health_endpoint_returns_ok(client: FlaskClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
