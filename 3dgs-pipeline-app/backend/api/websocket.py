import asyncio
from fastapi import APIRouter, WebSocket

router = APIRouter()

@router.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        # This is a placeholder. In a real app, you'd send logs from the pipeline.
        await websocket.send_json({"type": "log", "message": "Pipeline log message"})
        await asyncio.sleep(1)
