"""Module-level entry point.

Lets the app be started with:

    python -m app

which is a more conventional Python invocation than
``python -m app.main``. Both still work; this file delegates to
``app.main.create_app`` so there is a single source of truth for the
Flask app factory.
"""
from __future__ import annotations

from app.main import create_app


def main() -> None:
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
