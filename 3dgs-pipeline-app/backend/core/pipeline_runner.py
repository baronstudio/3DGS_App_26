"""
pipeline_runner.py — Full orchestrator for the 3DGS pipeline.

Step numbering:
  1  Import       (handled at project creation — skipped here)
  2  Extract      FFmpeg frame extraction
  3  RC           RealityCapture alignment
  4  LFS          LichtFeld Studio 3DGS training
  5  Export       Copy PLY/splat to export/
  6  Blender      SplatForge scene export
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session

from backend.api.websocket import broadcast
from backend.core.steps.step_blender import run_blender
from backend.core.steps.step_export import run_export
from backend.core.steps.step_extract import run_extract
from backend.core.steps.step_lfs import run_lfs
from backend.core.steps.step_rc import run_rc
from backend.db.database import engine
from backend.models.project import Project

PROJECTS_DIR = Path(__file__).parents[2] / "projects"

# ── Pause / Abort control ────────────────────────────────────────────────────

_abort_flags: dict[str, bool] = {}
_pause_events: dict[str, asyncio.Event] = {}

_STEP_NAMES: dict[int, str] = {
    1: "import",
    2: "extract",
    3: "rc",
    4: "lfs",
    5: "export",
    6: "blender",
}

_STEP_RUNNERS = {
    2: run_extract,
    3: run_rc,
    4: run_lfs,
    5: run_export,
    6: run_blender,
}


def _debug(msg: str) -> None:
    """Print a timestamped [WIZARD-DEBUG] line to the CLI."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
    print(f"[WIZARD-DEBUG {ts}] {msg}", flush=True)


def request_abort(project_id: str) -> None:
    """Signal the running pipeline for this project to abort."""
    _abort_flags[project_id] = True
    # Unblock any paused coroutine so it can observe the abort flag.
    event = _pause_events.get(project_id)
    if event:
        event.set()


def request_pause(project_id: str) -> None:
    """Pause the pipeline after the current sub-operation completes."""
    event = _pause_events.get(project_id)
    if event:
        event.clear()


def request_resume(project_id: str) -> None:
    """Resume a paused pipeline."""
    event = _pause_events.get(project_id)
    if event:
        event.set()


# ── DB helpers ───────────────────────────────────────────────────────────────

def _get_project(project_id: str) -> Project | None:
    with Session(engine) as session:
        return session.get(Project, project_id)


def _update_project(project_id: str, **kwargs) -> None:
    with Session(engine) as session:
        project = session.get(Project, project_id)
        if not project:
            return
        for key, val in kwargs.items():
            if key == "_step_status_dict":
                project.set_step_status(val)
            else:
                setattr(project, key, val)
        project.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        session.add(project)
        session.commit()


# ── Main orchestrator ────────────────────────────────────────────────────────

async def run_pipeline(
    project_id: str,
    start_from_step: int = 1,
    settings: dict = {},
) -> None:
    project = _get_project(project_id)
    if not project:
        _debug(f"run_pipeline called — project {project_id} NOT FOUND")
        await broadcast("pipeline", "ERROR", f"Project {project_id} not found")
        return

    project_path = PROJECTS_DIR / project.slug

    # ── Debug: log invocation context ────────────────────────────────────────
    existing_statuses = project.get_step_status()
    _debug(
        f"run_pipeline CALLED — project='{project.name}' ({project_id})"
        f"  start_from_step={start_from_step}"
        f"  DB current_step={project.current_step}"
        f"  DB step_status={existing_statuses}"
    )
    await broadcast(
        "pipeline", "DEBUG",
        f"[WIZARD-DEBUG] run_pipeline called: project='{project.name}'"
        f" start_from_step={start_from_step}"
        f" DB_current_step={project.current_step}"
        f" DB_step_status={existing_statuses}",
    )

    # Initialise abort / pause state for this run
    _abort_flags[project_id] = False
    pause_event = asyncio.Event()
    pause_event.set()  # Not paused initially
    _pause_events[project_id] = pause_event

    step_status = project.get_step_status()

    # Step 1 is always already done (handled at project creation).
    # Each call runs exactly ONE step — the user validates and triggers the next one.
    actual_start = max(start_from_step, 2)

    _debug(f"  → actual_start resolved to step {actual_start} ({_STEP_NAMES.get(actual_start, '?')})")

    try:
        for step in range(actual_start, actual_start + 1):
            step_name = _STEP_NAMES[step]

            # ── Abort check ────────────────────────────────────────────────
            if _abort_flags.get(project_id):
                _debug(f"  → ABORT flag set before step {step} — aborting")
                step_status[str(step)] = "aborted"
                _update_project(
                    project_id,
                    error_message="Pipeline aborted by user",
                    _step_status_dict=step_status,
                )
                await broadcast(
                    "pipeline", "WARNING",
                    f"Pipeline aborted for project {project_id}",
                    data={"status": "aborted", "project_id": project_id},
                )
                return

            # ── Pause check (blocks until resumed) ────────────────────────
            await pause_event.wait()

            # Second abort check in case abort was set while paused
            if _abort_flags.get(project_id):
                _debug(f"  → ABORT flag set after pause for step {step} — aborting")
                await broadcast(
                    "pipeline", "WARNING",
                    f"Pipeline aborted for project {project_id}",
                    data={"status": "aborted", "project_id": project_id},
                )
                return

            # ── Mark step as running ───────────────────────────────────────
            _debug(f"  → Step {step} ({step_name.upper()}) — marking as RUNNING")
            step_status[str(step)] = "running"
            _update_project(
                project_id,
                current_step=step,
                _step_status_dict=step_status,
            )
            # Broadcast a "status" message so the frontend can update stepStatuses[step] = 'running'
            await broadcast(
                step_name, "INFO",
                f"▶ Step {step} ({step_name.upper()}) starting...",
                status="running",
            )

            # ── Execute step ───────────────────────────────────────────────
            try:
                runner = _STEP_RUNNERS[step]
                await runner(project_path, broadcast, settings)

                _debug(f"  → Step {step} ({step_name.upper()}) — DONE")
                step_status[str(step)] = "done"
                _update_project(project_id, _step_status_dict=step_status)
                # Broadcast "status" done + progress=1.0 so frontend marks step complete
                await broadcast(
                    step_name, "SUCCESS",
                    f"✔ Step {step} ({step_name.upper()}) complete."
                    f" ⏳ Waiting for user to click 'Validate & Continue'.",
                    progress=1.0,
                    status="done",
                )
                _debug(
                    f"  → Step {step} done — broadcast 'status=done' sent."
                    f" Frontend must wait for user click to advance wizard."
                )

            except Exception as exc:
                step_status[str(step)] = "error"
                exc_detail = f"[{type(exc).__name__}] {exc}" if str(exc) else type(exc).__name__
                _debug(f"  → Step {step} ({step_name.upper()}) — ERROR: {exc_detail}")
                _update_project(
                    project_id,
                    error_message=exc_detail,
                    _step_status_dict=step_status,
                )
                await broadcast(
                    step_name, "ERROR",
                    f"✖ Step {step} ({step_name.upper()}) failed: {exc_detail}",
                    status="error",
                )
                return

        # ── Pipeline complete (only when the last step, Blender, finishes) ──────
        if actual_start == 6:
            _debug(f"  → Full pipeline complete for project {project_id}")
            _update_project(project_id, current_step=6)
            await broadcast(
                "pipeline", "SUCCESS",
                f"🎉 Pipeline complete for project {project_id}",
                progress=1.0,
                data={"status": "complete", "project_id": project_id},
            )

    finally:
        _debug(f"  → run_pipeline cleanup for project {project_id}")
        _abort_flags.pop(project_id, None)
        _pause_events.pop(project_id, None)
