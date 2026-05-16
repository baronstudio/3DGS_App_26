from fastapi import APIRouter

router = APIRouter()

@router.post("/start")
def start_pipeline():
    return {"message": "Pipeline started"}

@router.post("/control")
def control_pipeline():
    return {"message": "Pipeline control"}

@router.get("/status")
def get_status():
    return {"status": "idle"}
