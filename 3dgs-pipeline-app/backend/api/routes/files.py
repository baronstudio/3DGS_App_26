from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from backend.db.database import get_session
from backend.models.project import Project

router = APIRouter()

PROJECTS_DIR = Path(__file__).parents[3] / "projects"


def get_slug_from_id(project_id: str, session: Session) -> str:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.slug


@router.get("/{project_id}/frames")
async def list_frames(project_id: str, session: Session = Depends(get_session)):
    slug = get_slug_from_id(project_id, session)
    frames_dir = PROJECTS_DIR / slug / "frames"

    if not frames_dir.exists():
        return {"frames": [], "total": 0, "blurry_count": 0}

    files = sorted(
        [f for f in frames_dir.iterdir() if f.suffix.lower() in {".jpg", ".jpeg", ".png"}],
        key=lambda f: f.name,
    )

    if not files:
        return {"frames": [], "total": 0, "blurry_count": 0}

    sizes = [f.stat().st_size for f in files]
    threshold_5pct = sorted(sizes)[max(0, int(len(sizes) * 0.05) - 1)] if sizes else 0

    frames = []
    blurry_count = 0
    for f in files:
        size = f.stat().st_size
        potentially_blurry = size <= threshold_5pct
        if potentially_blurry:
            blurry_count += 1
        frames.append({
            "filename": f.name,
            "path": (Path(slug) / "frames" / f.name).as_posix(),
            "size_bytes": size,
            "url": f"/static/{slug}/frames/{f.name}",
            "potentially_blurry": potentially_blurry,
        })

    return {"frames": frames, "total": len(frames), "blurry_count": blurry_count}


class DeleteFramesBody(BaseModel):
    filenames: List[str]


@router.delete("/{project_id}/frames")
async def delete_frames(
    project_id: str,
    body: DeleteFramesBody,
    session: Session = Depends(get_session),
):
    slug = get_slug_from_id(project_id, session)
    frames_dir = PROJECTS_DIR / slug / "frames"

    deleted = 0
    for filename in body.filenames:
        target = frames_dir / Path(filename).name  # prevent path traversal
        if target.exists() and target.is_file():
            target.unlink()
            deleted += 1

    remaining = len(list(frames_dir.glob("*"))) if frames_dir.exists() else 0
    return {"deleted": deleted, "remaining": remaining}


@router.get("/{project_id}/export")
async def list_export_files(project_id: str, session: Session = Depends(get_session)):
    slug = get_slug_from_id(project_id, session)
    export_dir = PROJECTS_DIR / slug / "export"

    if not export_dir.exists():
        return {"files": []}

    files = [
        {
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "url": f"/static/{slug}/export/{f.name}",
        }
        for f in sorted(export_dir.iterdir(), key=lambda f: f.name)
        if f.is_file()
    ]
    return {"files": files}
