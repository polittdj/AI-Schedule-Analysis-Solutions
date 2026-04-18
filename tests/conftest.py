"""Shared pytest fixtures for the Schedule Forensics test suite."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app


@pytest.fixture(scope="session")
def app() -> Flask:
    flask_app = create_app()
    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture()
def client(app: Flask) -> Iterator[FlaskClient]:
    with app.test_client() as test_client:
        yield test_client
