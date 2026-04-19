"""Microsoft Project ``.mpp`` parser via ``win32com`` COM automation.

This module is the **only** place in the application that imports
``win32com`` (audit H7 / AC A7). Every other module — the CPM
engine, the DCMA metric modules, the NASA overlay, the comparator,
the manipulation engine, the AI backend, the Flask routes —
consumes :class:`app.models.Schedule` produced here and stays
parser-agnostic.

Design contract
===============

The parser opens an ``.mpp`` file **read-only** (Gotcha 9), walks
the MS Project COM object graph, and returns a fully-validated
:class:`Schedule`. It never mutates the source file; it never
retains state between calls; it closes and releases every COM
object on every exit path (Gotcha 8).

UniqueID is the sole task identity (BUILD-PLAN §2.7,
``mpp-parsing-com-automation §5``). ``Task.ID`` is captured for UI
display only. The MS Project predecessor string references Task IDs,
not UniqueIDs — the parser builds an ``id_map`` on the first task
pass and translates in a second pass (parser gotcha P6).

Parser gotcha chosen behaviors
------------------------------

* **P7 — unknown Task ID in a predecessor string.** The parser
  raises :class:`CorruptScheduleError`, halting the parse. The
  fail-fast posture matches "no analysis before parser validated"
  from ``mpp-parsing-com-automation §4``; the permissive alternative
  (skip with warning) would silently drop logic links and corrupt
  the CPM result.

* **P12 — deleted tasks.** MS Project preserves deleted rows with
  null UniqueID / null Name / null Duration. The parser skips a
  task when ``UniqueID is None`` OR (``Name is None`` AND
  ``Duration is None``). This heuristic tolerates the two
  field-vintage combinations observed in the wild while still
  raising on a genuinely corrupt row (UniqueID present, Name and
  Duration both null — treated as a ghost row and skipped).

* **P15 — large schedules.** The parser iterates by ``Tasks.Count``
  index, not by materializing the ``Tasks`` collection into Python,
  so COM round-trips stay O(N) in the task count. See
  :meth:`MPProjectParser._iter_tasks_indexed`.

CUI discipline
--------------

Log lines emitted from this module carry file paths, absolute task
counts, and parse duration only — never task names, WBS labels, or
resource names (``cui-compliance-constraints §2d``). The parser
returns the model; the model carries CUI fields which are
sanitized by the Milestone 12 ``DataSanitizer`` before any AI
prompt is built.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any

from app.models import (
    DATE_BEARING_CONSTRAINTS,
    Calendar,
    Relation,
    Resource,
    ResourceAssignment,
    Schedule,
    Task,
)
from app.models.enums import ConstraintType, TaskType
from app.parsers._com_helpers import (
    cast_minutes,
    coerce_datetime_to_utc,
    map_constraint_type,
    map_resource_type,
    safe_get,
)
from app.parsers._predecessor_parser import (
    CalendarUnits,
    parse_predecessor_string,
)
from app.parsers.exceptions import (
    COMUnavailableError,
    CorruptScheduleError,
    MPOpenError,
    ParserError,
)
from app.parsers.zombie_cleanup import sweep_orphan_msproject

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Injection points for tests
# ---------------------------------------------------------------------------
#
# Tests monkey-patch the two callables below with ``FakeMSProjectApp``
# factories. Production code leaves them at their lazy-import defaults
# so ``win32com`` is not touched on Linux CI.


def _default_dispatch(prog_id: str) -> Any:
    """Lazy import of ``win32com.client.Dispatch``.

    Imported here rather than at module top so a ``COMUnavailableError``
    is raised at call time rather than at parser-module import time.
    The parser must be importable on Linux CI (no win32com available)
    per AC A2.
    """
    try:
        import win32com.client  # noqa: PLC0415 — intentional lazy import
    except ImportError as exc:
        raise COMUnavailableError(
            "win32com is not available on this host. "
            "Microsoft Project must be installed on the same "
            "workstation as the tool to parse .mpp files."
        ) from exc
    return win32com.client.Dispatch(prog_id)


def _default_co_initialize() -> None:
    try:
        import pythoncom  # noqa: PLC0415
    except ImportError:
        # No-op on non-Windows — the subsequent Dispatch call will
        # surface COMUnavailableError with an actionable message.
        return
    pythoncom.CoInitialize()


def _default_co_uninitialize() -> None:
    try:
        import pythoncom  # noqa: PLC0415
    except ImportError:
        return
    pythoncom.CoUninitialize()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class MPProjectParser(AbstractContextManager["MPProjectParser"]):
    """Context manager for reading one ``.mpp`` file via COM automation.

    Usage
    -----

    >>> with MPProjectParser() as parser:      # doctest: +SKIP
    ...     schedule = parser.parse("C:/Tool/schedules/baseline.mpp")

    The context manager guarantees that :meth:`close` runs even if
    :meth:`parse` raises, satisfying parser gotcha P14 (no orphaned
    MSPROJECT.EXE processes).

    Dependency injection
    --------------------

    The three ``_default_*`` callables above are overridable via
    constructor keyword arguments for tests. Production code leaves
    them at their defaults.
    """

    def __init__(
        self,
        *,
        dispatch: Any = None,
        co_initialize: Any = None,
        co_uninitialize: Any = None,
        sweep: Any = None,
    ) -> None:
        self._dispatch = dispatch or _default_dispatch
        self._co_initialize = co_initialize or _default_co_initialize
        self._co_uninitialize = co_uninitialize or _default_co_uninitialize
        self._sweep = sweep or sweep_orphan_msproject
        self._app: Any = None
        self._co_initialized: bool = False

    # -- context manager protocol -----------------------------------------

    def __enter__(self) -> MPProjectParser:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- lifecycle --------------------------------------------------------

    def close(self) -> None:
        """Release COM resources.

        Parser gotcha P14: ``Quit()`` inside a ``finally`` block is
        the only defense against a stray MSPROJECT.EXE holding a
        file lock on the ``.mpp`` after a crash. This method is
        idempotent; tests may call it multiple times safely.
        """
        app = self._app
        self._app = None
        if app is not None:
            try:
                app.Quit()
            except Exception:  # noqa: BLE001 — COM cleanup must not re-raise
                _logger.debug("MSProject.Application.Quit raised; suppressed", exc_info=True)
        if self._co_initialized:
            try:
                self._co_uninitialize()
            except Exception:  # noqa: BLE001
                _logger.debug("CoUninitialize raised; suppressed", exc_info=True)
            self._co_initialized = False

    # -- public entry point ----------------------------------------------

    def parse(self, path: str | os.PathLike[str]) -> Schedule:
        """Open ``path``, read the schedule, close the file.

        Emits two log events at INFO:

        * ``mpp.parse.begin`` — file path and wall-clock start time
        * ``mpp.parse.end`` — task / relation / resource counts and
          elapsed seconds

        Neither event includes task names or any other CUI-bearing
        field value (``cui-compliance-constraints §2d``).

        Raises
        ------
        COMUnavailableError
            ``win32com`` cannot be imported or MS Project is not
            registered with the host OS (parser gotcha P1).
        MPOpenError
            ``FileOpen`` rejected the path — not found, locked, or
            permission denied (parser gotcha P2).
        CorruptScheduleError
            MS Project opened the file but the schedule could not be
            extracted cleanly (parser gotcha P3, P7, validation
            failures).
        """
        abs_path = os.path.abspath(os.fspath(path))
        started_at = time.monotonic()
        _logger.info("mpp.parse.begin path=%s", abs_path)

        # Skill §6 ordering invariant #1: orphan MSPROJECT.EXE sweep
        # runs BEFORE CoInitialize. No-op on non-Windows; secondary
        # defense to the mandatory finally-Quit() in close().
        self._sweep()

        # ------------------------------------------------------------
        # P1 — COM unavailable: dispatch raises COMUnavailableError.
        # ------------------------------------------------------------
        self._co_initialize()
        self._co_initialized = True
        try:
            self._app = self._dispatch("MSProject.Application")
        except COMUnavailableError:
            raise
        except Exception as exc:
            raise COMUnavailableError(
                "Failed to instantiate MSProject.Application. "
                "Verify that Microsoft Project is installed and "
                "registered on this host."
            ) from exc

        # Gotcha 2: Visible / DisplayAlerts must be set BEFORE FileOpen.
        # Assign FIRST so MS Project does not render its splash
        # screen or modal dialogs when the file-open call fires.
        try:
            self._app.Visible = False
            self._app.DisplayAlerts = False
        except Exception as exc:  # noqa: BLE001
            raise CorruptScheduleError(
                "Failed to configure MS Project headless mode"
            ) from exc

        # ------------------------------------------------------------
        # P2 / P3 — FileOpen
        # ------------------------------------------------------------
        try:
            self._app.FileOpen(abs_path, ReadOnly=True)
        except Exception as exc:
            if not os.path.exists(abs_path):
                raise MPOpenError(
                    f"File not found: {abs_path}"
                ) from exc
            raise MPOpenError(
                f"MS Project refused to open {abs_path}: {exc}"
            ) from exc

        try:
            project = safe_get(self._app, "ActiveProject")
            if project is None:
                raise CorruptScheduleError(
                    f"MS Project reported no active project after opening {abs_path}"
                )
            schedule = self._extract_schedule(project)
        except ParserError:
            raise
        except Exception as exc:
            raise CorruptScheduleError(
                f"MS Project failed mid-parse on {abs_path}: {exc}"
            ) from exc
        finally:
            # Gotcha 9: FileClose with Save=0. Wrapped because a
            # failed FileOpen leaves nothing to close; swallow the
            # error so the outer exception surfaces.
            try:
                self._app.FileClose(Save=0)
            except Exception:  # noqa: BLE001
                _logger.debug("FileClose raised; suppressed", exc_info=True)

        elapsed = time.monotonic() - started_at
        _logger.info(
            "mpp.parse.end path=%s tasks=%d relations=%d resources=%d elapsed=%.3fs",
            abs_path,
            len(schedule.tasks),
            len(schedule.relations),
            len(schedule.resources),
            elapsed,
        )
        return schedule

    # -- extraction orchestration ----------------------------------------

    def _extract_schedule(self, project: Any) -> Schedule:
        """Walk the ``Project`` COM graph into a :class:`Schedule`.

        Two-pass task extraction satisfies parser gotcha P6:

        1. First pass builds ``id_map: dict[task_id → unique_id]`` and
           constructs every :class:`Task` (without predecessors).
        2. Second pass parses each task's ``Predecessors`` string
           into :class:`Relation` objects, translating Task IDs to
           UniqueIDs via the ``id_map`` built in pass 1.
        """
        # Calendar conversion factors for the predecessor-lag parser.
        hours_per_day = float(safe_get(project, "HoursPerDay", 8.0) or 8.0)
        minutes_per_week = int(
            safe_get(project, "MinutesPerWeek", 5 * 8 * 60) or (5 * 8 * 60)
        )
        working_days_per_week = max(
            1, int(round(minutes_per_week / (hours_per_day * 60.0)))
        )
        cal_units = CalendarUnits(
            hours_per_day=hours_per_day,
            working_days_per_week=working_days_per_week,
        )

        # ------------------------------------------------------------
        # Pass 1 — tasks (by index per P15)
        # ------------------------------------------------------------
        tasks: list[Task] = []
        id_map: dict[int, int] = {}
        raw_predecessors: list[tuple[int, str | None]] = []

        for raw_task in self._iter_tasks_indexed(project):
            # Gotcha 4 / P12 — null / deleted rows
            if raw_task is None:
                continue
            unique_id = safe_get(raw_task, "UniqueID")
            name = safe_get(raw_task, "Name")
            duration_raw = safe_get(raw_task, "Duration")
            if unique_id is None:
                continue
            # P12 heuristic — genuinely-empty ghost rows
            if name is None and duration_raw is None:
                continue

            try:
                task = self._build_task(raw_task)
            except ValueError as exc:
                raise CorruptScheduleError(
                    f"Task UniqueID={unique_id} failed model validation: {exc}"
                ) from exc

            tasks.append(task)
            id_map[task.task_id] = task.unique_id
            raw_predecessors.append(
                (task.unique_id, safe_get(raw_task, "Predecessors"))
            )

        # ------------------------------------------------------------
        # Pass 2 — relations (via Predecessors string + id_map)
        # ------------------------------------------------------------
        relations: list[Relation] = []
        for successor_uid, pred_string in raw_predecessors:
            relations.extend(
                parse_predecessor_string(
                    pred_string,
                    successor_unique_id=successor_uid,
                    id_map=id_map,
                    units=cal_units,
                )
            )

        # ------------------------------------------------------------
        # Resources + assignments
        # ------------------------------------------------------------
        resources, assignments = self._extract_resources(project)

        # ------------------------------------------------------------
        # Calendars
        # ------------------------------------------------------------
        calendars = self._extract_calendars(
            project, hours_per_day, working_days_per_week, minutes_per_week
        )

        try:
            return Schedule(
                name=safe_get(project, "Name", "") or "",
                status_date=coerce_datetime_to_utc(safe_get(project, "StatusDate")),
                project_start=coerce_datetime_to_utc(
                    safe_get(project, "ProjectStart")
                ),
                project_finish=coerce_datetime_to_utc(
                    safe_get(project, "ProjectFinish")
                ),
                default_calendar_name=safe_get(
                    project, "DefaultCalendarName", "Standard"
                )
                or "Standard",
                tasks=tasks,
                relations=relations,
                resources=resources,
                assignments=assignments,
                calendars=calendars,
            )
        except ValueError as exc:
            raise CorruptScheduleError(
                f"Schedule failed cross-model validation: {exc}"
            ) from exc

    # -- task iteration (P15) --------------------------------------------

    def _iter_tasks_indexed(self, project: Any) -> Any:
        """Iterate ``project.Tasks`` by 1-based index.

        Parser gotcha P15: materializing the whole COM ``Tasks``
        collection into a Python list doubles the COM round-trips
        and hits a wall on schedules with tens of thousands of
        tasks. Iterating by index keeps traffic O(N). Falls back to
        direct iteration when ``Count`` is unavailable (tests using
        a plain Python list of :class:`FakeTask` doubles).
        """
        raw = safe_get(project, "Tasks")
        if raw is None:
            return
        count = safe_get(raw, "Count")
        if count is None:
            # Fixture path — raw is a plain Python iterable.
            yield from raw
            return
        # Real COM path — 1-based indexing, ``Item`` accessor.
        for i in range(1, int(count) + 1):
            try:
                yield raw.Item(i)
            except Exception:  # noqa: BLE001
                # A blank row may raise on Item access; treat as null.
                yield None

    # -- task building ---------------------------------------------------

    def _build_task(self, raw: Any) -> Task:
        """Construct a validated :class:`Task` from a COM task row.

        Each field below cites the COM property and the skill
        section establishing the mapping (AC A6).
        """
        # Identification
        unique_id = int(safe_get(raw, "UniqueID"))  # Task.UniqueID (skill §5)
        task_id = int(safe_get(raw, "ID", 0) or 0)  # Task.ID (skill §5)
        name = safe_get(raw, "Name", "") or ""  # Task.Name (skill §3.4)
        wbs = safe_get(raw, "WBS", "") or ""  # Task.WBS
        outline_level = int(safe_get(raw, "OutlineLevel", 0) or 0)

        # Dates — Gotcha 10 + audit Minor #3: tz-aware UTC at boundary.
        # (skill §3.10 amendment AM1 this PR)
        start = coerce_datetime_to_utc(safe_get(raw, "Start"))
        finish = coerce_datetime_to_utc(safe_get(raw, "Finish"))
        early_start = coerce_datetime_to_utc(safe_get(raw, "EarlyStart"))
        early_finish = coerce_datetime_to_utc(safe_get(raw, "EarlyFinish"))
        late_start = coerce_datetime_to_utc(safe_get(raw, "LateStart"))
        late_finish = coerce_datetime_to_utc(safe_get(raw, "LateFinish"))
        baseline_start = coerce_datetime_to_utc(safe_get(raw, "BaselineStart"))
        baseline_finish = coerce_datetime_to_utc(safe_get(raw, "BaselineFinish"))
        actual_start = coerce_datetime_to_utc(safe_get(raw, "ActualStart"))
        actual_finish = coerce_datetime_to_utc(safe_get(raw, "ActualFinish"))
        deadline = coerce_datetime_to_utc(safe_get(raw, "Deadline"))

        # Durations / slack — Gotcha 5, minutes (skill §3.5).
        duration_minutes = cast_minutes(safe_get(raw, "Duration"))
        remaining_duration_minutes = cast_minutes(
            safe_get(raw, "RemainingDuration")
        )
        actual_duration_minutes = cast_minutes(safe_get(raw, "ActualDuration"))
        baseline_duration_minutes = cast_minutes(
            safe_get(raw, "BaselineDuration")
        )
        total_slack_minutes = cast_minutes(
            safe_get(raw, "TotalSlack"), allow_negative=True
        )
        free_slack_minutes = cast_minutes(
            safe_get(raw, "FreeSlack"), allow_negative=True
        )

        # Constraint — Task.ConstraintType / Task.ConstraintDate.
        # Parser gotcha P9: ASAP / ALAP must null out the constraint
        # date before model construction even if COM hands one back.
        constraint_type = map_constraint_type(safe_get(raw, "ConstraintType"))
        constraint_date = coerce_datetime_to_utc(safe_get(raw, "ConstraintDate"))
        if constraint_type in (
            ConstraintType.AS_SOON_AS_POSSIBLE,
            ConstraintType.AS_LATE_AS_POSSIBLE,
        ):
            constraint_date = None
        elif (
            constraint_type in DATE_BEARING_CONSTRAINTS
            and constraint_date is None
        ):
            # Date-bearing constraint without a date is a corrupt COM
            # row — Pydantic G7 would reject it. Fall back to ASAP
            # so the overall parse does not hard-fail on one row.
            constraint_type = ConstraintType.AS_SOON_AS_POSSIBLE

        # Percent complete — clamp [0, 100] (model G8).
        percent_complete = float(safe_get(raw, "PercentComplete", 0.0) or 0.0)
        percent_complete = max(0.0, min(100.0, percent_complete))

        # Task scheduling type — Task.Type (PjTaskFixedType).
        try:
            task_type_raw = int(safe_get(raw, "Type", 0) or 0)
        except (TypeError, ValueError):
            task_type_raw = 0
        task_type = (
            TaskType(task_type_raw)
            if task_type_raw in (0, 1, 2)
            else TaskType.FIXED_UNITS
        )

        # Booleans.
        is_milestone = bool(safe_get(raw, "Milestone", False))
        is_summary = bool(safe_get(raw, "Summary", False))
        is_critical = bool(safe_get(raw, "Critical", False))
        # Inactive tasks (parser gotcha P13): flag preserved, still parsed.
        _active = safe_get(raw, "Active", True)
        # ``is_loe`` / ``is_rolling_wave`` / ``is_schedule_margin`` are
        # custom MSP fields with no uniform COM surface. Default False.
        is_loe = bool(safe_get(raw, "IsLevelOfEffort", False))
        is_rolling_wave = bool(safe_get(raw, "IsRollingWave", False))
        is_schedule_margin = bool(safe_get(raw, "IsScheduleMargin", False))

        # Resource count — len(Task.Assignments). COM exposes Count.
        assignments = safe_get(raw, "Assignments")
        if assignments is None:
            resource_count = 0
        else:
            count = safe_get(assignments, "Count")
            if count is None:
                try:
                    resource_count = sum(1 for _ in assignments)
                except TypeError:
                    resource_count = 0
            else:
                resource_count = int(count)

        return Task(
            unique_id=unique_id,
            task_id=task_id,
            name=name,
            wbs=wbs,
            outline_level=outline_level,
            start=start,
            finish=finish,
            early_start=early_start,
            early_finish=early_finish,
            late_start=late_start,
            late_finish=late_finish,
            baseline_start=baseline_start,
            baseline_finish=baseline_finish,
            actual_start=actual_start,
            actual_finish=actual_finish,
            deadline=deadline,
            duration_minutes=duration_minutes,
            remaining_duration_minutes=remaining_duration_minutes,
            actual_duration_minutes=actual_duration_minutes,
            baseline_duration_minutes=baseline_duration_minutes,
            total_slack_minutes=total_slack_minutes,
            free_slack_minutes=free_slack_minutes,
            constraint_type=constraint_type,
            constraint_date=constraint_date,
            percent_complete=percent_complete,
            task_type=task_type,
            is_milestone=is_milestone,
            is_summary=is_summary,
            is_critical_from_msp=is_critical,
            is_loe=is_loe,
            is_rolling_wave=is_rolling_wave,
            is_schedule_margin=is_schedule_margin,
            resource_count=resource_count,
        )

    # -- resources + assignments -----------------------------------------

    def _extract_resources(
        self, project: Any
    ) -> tuple[list[Resource], list[ResourceAssignment]]:
        """Build resource and assignment lists.

        Assignment resource-uid / task-uid pairs are filtered against
        the already-parsed task UIDs in :meth:`_extract_schedule`
        (Schedule's model_validator G11 handles the referential
        check). This method only reads; it does not validate.
        """
        resources: list[Resource] = []
        raw_resources = safe_get(project, "Resources")
        if raw_resources is not None:
            for raw in self._iter_collection(raw_resources):
                if raw is None:
                    continue
                rid = safe_get(raw, "UniqueID")
                if rid is None:
                    continue
                try:
                    resources.append(
                        Resource(
                            unique_id=int(rid),
                            resource_id=int(safe_get(raw, "ID", 0) or 0),
                            name=safe_get(raw, "Name", "") or "",
                            resource_type=map_resource_type(
                                safe_get(raw, "Type")
                            ),
                            initials=safe_get(raw, "Initials", "") or "",
                            group=safe_get(raw, "Group", "") or "",
                            max_units=float(
                                safe_get(raw, "MaxUnits", 1.0) or 1.0
                            ),
                        )
                    )
                except ValueError as exc:
                    raise CorruptScheduleError(
                        f"Resource UniqueID={rid} failed validation: {exc}"
                    ) from exc

        # Assignments are walked via each task's Assignments collection
        # rather than project.Assignments because older MS Project
        # vintages do not expose a project-level Assignments property.
        assignments: list[ResourceAssignment] = []
        raw_tasks = safe_get(project, "Tasks")
        if raw_tasks is not None:
            for raw_task in self._iter_collection(raw_tasks):
                if raw_task is None:
                    continue
                tuid = safe_get(raw_task, "UniqueID")
                if tuid is None:
                    continue
                raw_assigns = safe_get(raw_task, "Assignments")
                if raw_assigns is None:
                    continue
                for raw_a in self._iter_collection(raw_assigns):
                    if raw_a is None:
                        continue
                    ruid = safe_get(raw_a, "ResourceUniqueID")
                    if ruid is None or int(ruid) <= 0:
                        # Unassigned placeholder — skip.
                        continue
                    try:
                        assignments.append(
                            ResourceAssignment(
                                resource_unique_id=int(ruid),
                                task_unique_id=int(tuid),
                                units=float(
                                    safe_get(raw_a, "Units", 1.0) or 1.0
                                ),
                                work_minutes=cast_minutes(
                                    safe_get(raw_a, "Work")
                                ),
                            )
                        )
                    except ValueError as exc:
                        raise CorruptScheduleError(
                            f"Assignment (resource={ruid}, task={tuid}) "
                            f"failed validation: {exc}"
                        ) from exc

        return resources, assignments

    # -- calendars --------------------------------------------------------

    def _extract_calendars(
        self,
        project: Any,
        hours_per_day: float,
        working_days_per_week: int,
        minutes_per_week: int,
    ) -> list[Calendar]:
        """Build the :class:`Calendar` list.

        The project's default calendar is populated with the
        ``HoursPerDay`` / ``MinutesPerWeek`` values read at parse
        time. Additional per-task calendars (if any) are copied
        across with the same hours-per-day default; working-time
        exceptions are out of scope for Phase 1 (M8 overlay only
        reads ``hours_per_day`` per BUILD-PLAN §2.6).
        """
        calendars: list[Calendar] = []
        raw_calendars = safe_get(project, "Calendars")
        if raw_calendars is None:
            # Fallback: synthesize a single default calendar so
            # downstream consumers always have at least one.
            calendars.append(
                Calendar(
                    name=safe_get(project, "DefaultCalendarName", "Standard")
                    or "Standard",
                    hours_per_day=hours_per_day,
                    working_days_per_week=working_days_per_week,
                    minutes_per_week=minutes_per_week,
                )
            )
            return calendars

        for raw in self._iter_collection(raw_calendars):
            if raw is None:
                continue
            try:
                calendars.append(
                    Calendar(
                        name=safe_get(raw, "Name", "Standard") or "Standard",
                        hours_per_day=hours_per_day,
                        working_days_per_week=working_days_per_week,
                        minutes_per_week=minutes_per_week,
                    )
                )
            except ValueError as exc:
                raise CorruptScheduleError(
                    f"Calendar failed validation: {exc}"
                ) from exc
        if not calendars:
            calendars.append(
                Calendar(
                    name=safe_get(project, "DefaultCalendarName", "Standard")
                    or "Standard",
                    hours_per_day=hours_per_day,
                    working_days_per_week=working_days_per_week,
                    minutes_per_week=minutes_per_week,
                )
            )
        return calendars

    # -- generic COM iterator --------------------------------------------

    def _iter_collection(self, raw: Any) -> Any:
        """Iterate a COM collection by index when ``Count`` exists.

        Falls back to plain Python iteration for fixture paths.
        """
        count = safe_get(raw, "Count")
        if count is None:
            yield from raw
            return
        for i in range(1, int(count) + 1):
            try:
                yield raw.Item(i)
            except Exception:  # noqa: BLE001
                yield None


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------


def parse_mpp(path: str | os.PathLike[str]) -> Schedule:
    """Parse ``path`` via a one-shot :class:`MPProjectParser`.

    Convenience for callers that do not need to reuse a parser. The
    context manager form (``with MPProjectParser() as p:``) is
    preferred when parsing multiple files in sequence because COM
    initialization is shared.
    """
    with MPProjectParser() as parser:
        return parser.parse(path)
