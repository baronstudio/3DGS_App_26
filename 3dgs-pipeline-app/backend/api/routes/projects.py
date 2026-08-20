import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.core.curate.select import DROP, KEEP
from backend.core.steps.step_analyze import (
    load_overrides,
    rebuild_selection,
    save_overrides,
)
from backend.db.database import get_session
from backend.models.project import Project

router = APIRouter()

PROJECTS_DIR = Path(__file__).parents[3] / "projects"


def get_project_path(slug: str) -> Path:
    return PROJECTS_DIR / slug


def _get_thumbnail_url(slug: str) -> Optional[str]:
    frames_dir = PROJECTS_DIR / slug / "frames"
    if not frames_dir.exists():
        return None
    for ext in (".jpg", ".jpeg", ".png"):
        files = sorted(frames_dir.glob(f"*{ext}"))
        if files:
            return f"/static/{slug}/frames/{files[0].name}"
    return None


def project_to_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "slug": project.slug,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "current_step": project.current_step,
        "step_status": project.get_step_status(),
        "input_video_path": project.input_video_path,
        "frame_count": project.frame_count,
        "settings_json": project.settings_json,
        "error_message": project.error_message,
        "thumbnail_url": _get_thumbnail_url(project.slug),
    }


class CreateProjectBody(BaseModel):
    name: str
    settings: Optional[dict] = None


class UpdateProjectBody(BaseModel):
    name: Optional[str] = None
    current_step: Optional[int] = None
    step_status: Optional[dict] = None
    settings_json: Optional[dict] = None
    error_message: Optional[str] = None


@router.post("/create")
async def create_project(
    body: CreateProjectBody, session: Session = Depends(get_session)
):
    slug = re.sub(r"[^a-z0-9_-]", "_", body.name.lower())

    project_path = get_project_path(slug)
    for subdir in ["input", "frames", "analysis", "report", "rc_output", "lfs_output", "export"]:
        (project_path / subdir).mkdir(parents=True, exist_ok=True)

    project = Project(
        name=body.name,
        slug=slug,
        settings_json=json.dumps(body.settings) if body.settings else "{}",
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    return project_to_dict(project)


@router.get("/")
async def list_projects(session: Session = Depends(get_session)):
    projects = session.exec(
        select(Project).order_by(Project.created_at.desc())
    ).all()
    return [project_to_dict(p) for p in projects]


@router.get("/{id}")
async def get_project(id: str, session: Session = Depends(get_session)):
    project = session.get(Project, id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    base = get_project_path(project.slug)
    result = project_to_dict(project)
    result["paths"] = {
        "input": (base / "input").as_posix(),
        "frames": (base / "frames").as_posix(),
        "rc_output": (base / "rc_output").as_posix(),
        "lfs_output": (base / "lfs_output").as_posix(),
        "export": (base / "export").as_posix(),
    }
    return result


@router.delete("/{id}")
async def delete_project(id: str, session: Session = Depends(get_session)):
    project = session.get(Project, id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_path = get_project_path(project.slug)
    if project_path.exists():
        shutil.rmtree(project_path)

    session.delete(project)
    session.commit()

    return {"deleted": id}


_ALLOWED_INPUT_EXTS = {".mp4", ".mov", ".srt"}


@router.get("/{id}/input-files")
async def list_input_files(id: str, session: Session = Depends(get_session)):
    project = session.get(Project, id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    input_dir = get_project_path(project.slug) / "input"
    if not input_dir.exists():
        return {"files": []}
    files = [
        {"filename": f.name, "size_bytes": f.stat().st_size}
        for f in sorted(input_dir.iterdir(), key=lambda f: f.name)
        if f.is_file() and f.suffix.lower() in _ALLOWED_INPUT_EXTS
    ]
    return {"files": files}


@router.post("/{id}/upload-input")
async def upload_input_file(
    id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    project = session.get(Project, id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    raw_name = Path(file.filename or "unnamed").name  # strip any directory component
    ext = Path(raw_name).suffix.lower()
    if ext not in _ALLOWED_INPUT_EXTS:
        raise HTTPException(
            status_code=400,
            detail="Only .mp4, .mov, or .srt files are accepted",
        )

    input_dir = get_project_path(project.slug) / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    target = input_dir / raw_name
    contents = await file.read()
    target.write_bytes(contents)

    return {"filename": raw_name, "size_bytes": len(contents)}


@router.delete("/{id}/input-files/{filename}")
async def delete_input_file(
    id: str,
    filename: str,
    session: Session = Depends(get_session),
):
    project = session.get(Project, id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Prevent path traversal by stripping any directory components
    safe_name = Path(filename).name
    target = get_project_path(project.slug) / "input" / safe_name

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    target.unlink()
    return {"deleted": safe_name}


@router.put("/{id}")
async def update_project(
    id: str,
    body: UpdateProjectBody,
    session: Session = Depends(get_session),
):
    project = session.get(Project, id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.name is not None:
        project.name = body.name
    if body.current_step is not None:
        project.current_step = body.current_step
    if body.step_status is not None:
        project.set_step_status(body.step_status)
    if body.settings_json is not None:
        project.settings_json = json.dumps(body.settings_json)
    if body.error_message is not None:
        project.error_message = body.error_message

    project.updated_at = datetime.utcnow()
    session.add(project)
    session.commit()
    session.refresh(project)

    return project_to_dict(project)


class PatchProjectBody(BaseModel):
    """Partial update. Anything omitted is left alone."""

    name: Optional[str] = None
    current_step: Optional[int] = None
    step_status: Optional[dict] = None
    error_message: Optional[str] = None
    # Deep-merged into settings_json: a project stores only the keys it really
    # overrides, so changing a default keeps propagating to it (CLAUDE.md §4).
    settings: Optional[dict] = None
    # Manual curation verdicts: {"frame_0007.jpg": "keep" | "drop" | null}.
    # null removes the override and hands the frame back to the automatic verdict.
    overrides: Optional[dict] = None


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@router.patch("/{id}")
async def patch_project(
    id: str,
    body: PatchProjectBody,
    session: Session = Depends(get_session),
):
    """Partial update, including the manual keep/drop overrides.

    Flipping a frame only rewrites overrides.json and re-derives selection.json
    from the existing scores — no image is re-read, so the gallery updates
    instantly instead of paying for a full re-analysis.
    """
    project = session.get(Project, id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.name is not None:
        project.name = body.name
    if body.current_step is not None:
        project.current_step = body.current_step
    if body.step_status is not None:
        project.set_step_status(body.step_status)
    if body.error_message is not None:
        project.error_message = body.error_message

    if body.settings is not None:
        try:
            current = json.loads(project.settings_json or "{}")
        except json.JSONDecodeError:
            current = {}
        project.settings_json = json.dumps(_deep_merge(current, body.settings))

    selection = None
    if body.overrides is not None:
        project_path = get_project_path(project.slug)
        overrides = load_overrides(project_path)
        for frame, verdict in body.overrides.items():
            safe = Path(frame).name  # never let a path escape analysis/
            if verdict is None:
                overrides.pop(safe, None)
            elif verdict in (KEEP, DROP):
                overrides[safe] = verdict
            else:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid override '{verdict}' for {safe}. Expected 'keep', 'drop' or null.",
                )
        save_overrides(project_path, overrides)
        selection = rebuild_selection(project_path)

    project.updated_at = datetime.utcnow()
    session.add(project)
    session.commit()
    session.refresh(project)

    return {**project_to_dict(project), "selection": selection}
