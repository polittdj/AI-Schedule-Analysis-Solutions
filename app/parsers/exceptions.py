"""Parser-layer exception hierarchy.

The Milestone 3 COM adapter raises one of the typed errors below at
every documented failure mode rather than leaking ``pywintypes`` /
``OSError`` / ``AttributeError`` to its callers. Downstream layers
(the upload route, the CPM engine, the manipulation engine) catch on
``ParserError`` and surface a specification-grade message to the
analyst per the Milestone 13 tool-to-user voice (``CLAUDE.md §8``).

All messages are CUI-safe by construction: the parser may only
reference file paths, file names, and aggregate counts in error text
per ``cui-compliance-constraints §2d``. Task names, WBS labels, and
resource names must never appear here or in any log line raised from
this module.
"""

from __future__ import annotations


class ParserError(Exception):
    """Root of the parser exception tree.

    Catching ``ParserError`` is the supported way for upstream Flask
    routes to recognize any parse-time failure without depending on
    the COM library being importable on the caller's platform (the
    parser is the only module that imports ``win32com``; see audit
    H7).
    """


class COMUnavailableError(ParserError):
    """Raised when the Microsoft Project COM server cannot be reached.

    Triggered when ``pywin32`` is not installed (non-Windows hosts,
    Linux CI runners) or when ``win32com.client.Dispatch`` raises
    because MS Project is not registered with the OS. The message is
    deliberately actionable — the analyst is told that MS Project must
    be installed locally on the same workstation per
    ``mpp-parsing-com-automation §1`` and ``CLAUDE.md §7``.
    """


class MPOpenError(ParserError):
    """Raised when ``app.FileOpen`` rejects the path.

    Distinct from :class:`CorruptScheduleError`: this signals "the
    file did not open" (not found, locked, wrong extension), not "the
    file opened but its contents are unreadable." Includes the
    absolute path the parser attempted to open so the analyst can
    confirm it matches the file in MS Project's recent-files list.
    """


class CorruptScheduleError(ParserError):
    """Raised when MS Project opens the file but extraction fails.

    Covers two distinct cases: (a) MS Project surfaces a COM error
    while iterating tasks / relations / resources, and (b) the
    parser detects a structural defect (for example, a predecessor
    string that points at a Task ID with no matching task) that makes
    the schedule unsafe to forward to the CPM engine. The originating
    error class is preserved as ``__cause__`` so the analyst can read
    the underlying MS Project diagnostic.
    """


class UnsupportedVersionError(ParserError):
    """Raised when the file format pre-dates the supported COM surface.

    Reserved for the case where MS Project agrees to open the file
    but the parser detects a vintage (pre-Project 2010, MPX export,
    etc.) that lacks fields the forensic engine requires. Phase 1
    treats this as fail-fast — the parser does not attempt a
    "best-effort" parse on unsupported vintages.
    """
