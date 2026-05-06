"""Shared pytest fixtures for the Schedule Forensics test suite."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app
from app.config import Config

# Per app/config.py Config.resolve_secret_key, the TESTING=True path
# returns an ephemeral SECRET_KEY per app instance. Setting this at
# conftest import time ensures every test that calls create_app() —
# directly or through a fixture — works without setting FLASK_SECRET_KEY
# in the environment. TESTING is read only by resolve_secret_key, so
# flipping it globally has no other behavioral effect on the suite.
Config.TESTING = True


@pytest.fixture(scope="session")
def app() -> Flask:
    return create_app()


@pytest.fixture()
def client(app: Flask) -> Iterator[FlaskClient]:
    with app.test_client() as test_client:
        yield test_client
