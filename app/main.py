"""Entry point for `python -m app.main`.

Boots the Flask development server on http://localhost:5000
per BUILD-PLAN.md §5 M1 file-by-file scope and AC2.

For production serving, use a WSGI server (gunicorn, waitress,
or similar) rather than Flask's built-in dev server. The dev
server is appropriate for local CUI-safe operation during
development and test.
"""

from app import create_app


def main() -> None:
    """Create the Flask app and run the development server."""
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
