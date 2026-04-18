# `app/parsers/` — MS Project `.mpp` Parser

## Purpose

Translate a Microsoft Project `.mpp` file into a validated
`app.models.Schedule` via `win32com` COM automation. This package
is the **only** place in the application that imports `win32com`
(audit H7 / M3 AC A7); every downstream module — the CPM engine,
the DCMA metric layer, the NASA overlay, the comparator, the
manipulation engine, the AI backend, the Flask routes — consumes
the parsed `Schedule` and stays parser-agnostic.

## Public API

```python
from app.parsers import MPProjectParser, parse_mpp

# One-shot:
schedule = parse_mpp("C:/Tool/schedules/baseline.mpp")

# Reusable:
with MPProjectParser() as parser:
    a = parser.parse("C:/Tool/schedules/period_a.mpp")
    b = parser.parse("C:/Tool/schedules/period_b.mpp")
```

Both entry points return `app.models.Schedule`. Errors are all
`ParserError` subclasses so callers can catch broadly.

### Errors

| Class | When it is raised |
|---|---|
| `COMUnavailableError` | `win32com` absent or MS Project not registered (parser gotcha P1) |
| `MPOpenError` | `FileOpen` rejected the path — not found, locked, wrong format (P2) |
| `CorruptScheduleError` | MS Project opened the file but extraction failed (P3, P7, model validation failures) |
| `UnsupportedVersionError` | File vintage pre-dates the supported COM surface |

All four descend from `ParserError`.

## Design Contract

* **Read-only.** `FileOpen(..., ReadOnly=True)` and `FileClose(Save=0)`
  (skill §3.9 / Gotcha 9). The parser never mutates the source file.
* **Headless.** `Visible = False` and `DisplayAlerts = False` are
  assigned **before** `FileOpen` to suppress MS Project modal dialogs
  (skill §3.2 / Gotcha 2).
* **Tz-aware UTC at the boundary.** COM returns naive locale-formatted
  datetimes (skill §3.10 / Gotcha 10). The parser attaches UTC at
  the boundary; every field on the returned `Schedule` carries a
  tz-aware datetime. This is the amendment **AM1** landed in the
  Milestone 3 PR: skill §3.10 now reads *"M3 COM adapter attaches
  UTC at the parser boundary; models carry tz-aware datetimes
  thereafter."*
* **UniqueID is the sole task identity** (BUILD-PLAN §2.7 / skill §5).
  `Task.ID` is captured for UI display only. The MS Project
  `Predecessors` column references Task IDs, not UniqueIDs — the
  parser builds an `id_map` in pass 1 and translates in pass 2
  (parser gotcha P6).
* **Durations / slack / lag in minutes** (skill §3.5 / Gotcha 5).
  Working-day conversion is the engine layer's responsibility
  (routed to `app/engine/duration.py` per BUILD-PLAN §5 M2 AC2
  amendment, landing in M4 or M5 when first consumer arrives —
  this is amendment **AM3** of this PR).

## Parser Gotcha Chosen Behaviors

| Gotcha | Chosen behavior | Rationale |
|---|---|---|
| **P7** — predecessor references a non-existent Task ID | **Raise** `CorruptScheduleError` | Silently dropping a logic link would corrupt the CPM result and hide a manipulation signal. Fail-fast matches "no analysis before parser validated" (skill §4). |
| **P12** — deleted / ghost task rows | Skip when `UniqueID is None` OR (`Name is None` AND `Duration is None`) | Tolerates the two field-vintage combinations observed in the wild while still rejecting a row with a present UniqueID and otherwise-null fields. |
| **P15** — schedules with 10k+ tasks | Iterate by `Count` + `Item(i)` rather than materializing `Tasks` | Real-COM target is <5 min on 10k tasks (unmockable in CI). The mocked fixture asserts the parse completes in <30 s. |

## CUI Discipline

Log lines from this package carry file paths, absolute task counts,
and parse-duration metrics only — never task names, WBS labels, or
resource names (`cui-compliance-constraints §2d`). The returned
`Schedule` carries CUI-bearing fields (`Task.name`, `Task.wbs`,
`Resource.name`); those are sanitized by the Milestone 12
`DataSanitizer` before any AI prompt is built.

## CI Skip Behavior

`win32com` is Windows-only (`pywin32>=306; sys_platform == 'win32'`
in `requirements.txt`). On Linux CI the parser module imports
cleanly — `win32com` is imported lazily inside `_default_dispatch`
— and a call to `parse_mpp(...)` surfaces `COMUnavailableError`
with an actionable message. Tests that would require a live COM
server are skipped explicitly via the dependency-injected
`dispatch` callable rather than via `pytest.importorskip`, which
keeps every gotcha path under test on Linux.

## Test Coverage

* `tests/test_parsers_exceptions.py` — exception hierarchy.
* `tests/test_parsers_com_helpers.py` — pure helper functions
  (date coercion, minutes cast, enum mappings, `safe_get`).
* `tests/test_parsers_predecessor.py` — MS Project predecessor
  string grammar, Task ID → UniqueID translation, lag-unit
  arithmetic.
* `tests/test_parsers_com_parser.py` — parser integration with
  synthetic COM-shaped doubles (`tests/fixtures/`). Covers every
  parser gotcha P1–P15.

No real `.mpp` fixtures are committed (CUI rule 2c).

## Milestone 4+ Consumers

The parser's only job is to hand downstream layers a validated
`Schedule`. The CPM engine (M4), DCMA metrics (M5–M7), NASA overlay
(M8), comparator (M9), driving-path tracer (M10), and manipulation
engine (M11) each accept `Schedule` as input and never re-enter
this module.
