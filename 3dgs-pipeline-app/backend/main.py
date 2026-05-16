import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# On Windows, asyncio defaults to SelectorEventLoop which does NOT support
# subprocesses. Force ProactorEventLoop so asyncio.create_subprocess_exec works.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import websocket
from backend.api.routes import files, pipeline, projects, settings
from backend.db.database import create_db_and_tables

PROJECTS_DIR = Path(__file__).parent.parent / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(websocket.router)

app.mount("/static", StaticFiles(directory=str(PROJECTS_DIR)), name="static")


@app.get("/")
def read_root():
    return {"Hello": "World"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
