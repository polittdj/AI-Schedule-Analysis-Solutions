"""Flask application factory for the Schedule Forensics tool.

Importing this module must not start a server or perform any side
effects that touch the JVM, COM, or the network. The factory is the
single entry point for constructing a configured Flask instance.
"""

from __future__ import annotations

from flask import Flask

from app.config import Config
from app.errors import register_error_handlers
from app.routes.health import health_bp


def create_app(config: type[Config] | Config | None = None) -> Flask:
    """Build and return a configured Flask application.

    Parameters
    ----------
    config
        Optional Config class or instance. Defaults to the module-level
        ``Config`` in ``app.config``.
    """
    app = Flask(__name__)
    app.config.from_object(config or Config)

    register_error_handlers(app)
    app.register_blueprint(health_bp)

    return app
