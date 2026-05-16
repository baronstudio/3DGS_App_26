from fastapi import APIRouter

router = APIRouter()

@router.get("/{project_id}/frames")
def list_frames(project_id: str):
    return {"frames": []}

@router.delete("/{project_id}/frames")
def delete_frames(project_id: str):
    return {"message": "Frames deleted"}

@router.get("/{project_id}/export")
def list_export_files(project_id: str):
    return {"files": []}
