"""Public API of the MS Project ``.mpp`` parser.

Importing this package is safe on every platform: the COM dispatch
is deferred to the point where ``MPProjectParser.parse`` runs, so
Linux CI can import the module and its test surface without
``pywin32`` installed.

``win32com`` is imported **only** inside :mod:`app.parsers.com_parser`
(audit H7 / M3 AC A7). Every other module of the application —
models, engine, comparator, manipulation, AI backend, web routes —
stays parser-agnostic by consuming :class:`app.models.Schedule`.
"""

from __future__ import annotations

from app.parsers.com_parser import MPProjectParser, parse_mpp
from app.parsers.exceptions import (
    COMUnavailableError,
    CorruptScheduleError,
    MPOpenError,
    ParserError,
    UnsupportedVersionError,
)

__all__ = [
    "COMUnavailableError",
    "CorruptScheduleError",
    "MPOpenError",
    "MPProjectParser",
    "ParserError",
    "UnsupportedVersionError",
    "parse_mpp",
]
