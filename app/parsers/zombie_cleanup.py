"""Orphan ``MSPROJECT.EXE`` startup sweep.

Skill §6 ordering invariant #1 (``mpp-parsing-com-automation``):
the parser must sweep orphan ``MSPROJECT.EXE`` processes **before**
``CoInitialize`` on every parse attempt. A Python crash between
``FileOpen`` and ``app.Quit()`` in a prior run can leave an
invisible ``MSPROJECT.EXE`` holding a file lock on the ``.mpp``;
the next parse attempt then hits Lessons Learned §10 item 6 ("Not
handling file locking") and gets an RPC failure or a read-only
copy.

The mandatory defense for this gotcha (``finally: app.Quit()``)
is implemented in :meth:`app.parsers.com_parser.MPProjectParser.close`.
This module is the secondary defense per skill §3.8: "consider a
startup check that kills orphaned processes."

Platform
--------

``taskkill`` is Windows-only. On any other platform this module's
sweep is a no-op — there is no ``MSPROJECT.EXE`` to kill and the
parser will fail downstream with :class:`COMUnavailableError`
anyway.

CUI note
--------

The sweep is process-scoped and does not read or touch ``.mpp``
files. No CUI data flows through this module.
"""

from __future__ import annotations

import logging
import subprocess
import sys

_logger = logging.getLogger(__name__)

# Windows process image name for MS Project.
_MSPROJECT_IMAGE_NAME = "MSPROJECT.EXE"


def sweep_orphan_msproject() -> None:
    """Kill any orphan ``MSPROJECT.EXE`` processes on Windows.

    Non-Windows platforms: no-op. On Windows, invokes
    ``taskkill /F /IM MSPROJECT.EXE`` with ``check=False`` so the
    common case (no orphans running) does not raise. The call
    output is suppressed so a long-running parse does not leak
    ``taskkill`` status lines into the analyst's log.

    Any unexpected exception from ``subprocess.run`` is logged at
    DEBUG and swallowed — the startup sweep is the *secondary*
    defense, and letting its failure abort a parse would defeat
    the purpose.
    """
    if sys.platform != "win32":
        return
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", _MSPROJECT_IMAGE_NAME],
            check=False,
            capture_output=True,
        )
    except Exception:  # noqa: BLE001 — secondary defense must not raise
        _logger.debug("taskkill sweep raised; suppressed", exc_info=True)
