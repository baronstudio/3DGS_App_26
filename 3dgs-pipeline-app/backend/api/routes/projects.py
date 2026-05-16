from fastapi import APIRouter

router = APIRouter()

@router.post("/create")
def create_project():
    return {"message": "Project created"}

@router.get("/")
def list_projects():
    return {"projects": []}

@router.get("/{id}")
def get_project(id: str):
    return {"project_id": id}

@router.delete("/{id}")
def delete_project(id: str):
    return {"message": f"Project {id} deleted"}
