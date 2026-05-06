"""Flask application factory for the Schedule Forensics tool.

Importing this module must not start a server or perform any side
effects that touch the JVM, COM, or the network. The factory is the
single entry point for constructing a configured Flask instance.
"""

from __future__ import annotations

from flask import Flask

from app.config import Config
from app.contracts import (
    ConstraintDrivenCrossVersionResult,
    ManipulationScoringResult,
    ManipulationScoringSummary,
    SeverityTier,
    SlackState,
)
from app.engine.manipulation_scoring import score_manipulation
from app.errors import register_error_handlers
from app.routes.ai_analyze import ai_analyze_bp
from app.routes.classification import classification_bp
from app.routes.health import health_bp

__all__ = (
    "ConstraintDrivenCrossVersionResult",
    "ManipulationScoringResult",
    "ManipulationScoringSummary",
    "SeverityTier",
    "SlackState",
    "create_app",
    "score_manipulation",
)


def create_app(config: type[Config] | Config | None = None) -> Flask:
    """Build and return a configured Flask application.

    Parameters
    ----------
    config
        Optional Config class or instance. Defaults to the module-level
        ``Config`` in ``app.config``.
    """
    resolved_config = config or Config
    config_cls: type[Config]
    if isinstance(resolved_config, type):
        config_cls = resolved_config
    else:
        config_cls = type(resolved_config)

    app = Flask(
        __name__,
        template_folder="web/templates",
    )
    app.config.from_object(resolved_config)
    app.config["SECRET_KEY"] = config_cls.resolve_secret_key()

    register_error_handlers(app)
    app.register_blueprint(health_bp)
    app.register_blueprint(classification_bp)
    app.register_blueprint(ai_analyze_bp)

    return app
