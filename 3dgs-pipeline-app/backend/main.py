from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import settings
from backend.api import websocket
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
# app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(websocket.router)


@app.get("/")
def read_root():
    return {"Hello": "World"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
