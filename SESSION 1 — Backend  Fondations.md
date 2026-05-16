## CONTEXT
Project: 3DGS Pipeline Web App (local, Windows)
Stack: FastAPI + Python 3.11 + SQLModel/SQLite + Pydantic v2
Working dir: c:\Travail\DEV\3DGS_App_26\3dgs-pipeline-app\
Python venv: .venv\ (already created, FastAPI/uvicorn/sqlmodel installed)

## CURRENT STATE OF FILES TO MODIFY

### backend/core/config.py (current — flat dict, needs Pydantic migration)
Uses plain dict with json.load. No Pydantic models. Stubs default to False.

### backend/api/websocket.py (current — placeholder)
Only sends "Pipeline log message" every second. No connection manager. No broadcast().

### backend/models/project.py (current — minimal)
Only 3 fields: id, name (SQLModel). Not complete.

### backend/db/database.py (current — not integrated)
Creates engine but create_db_and_tables() is never called.

### backend/main.py (current)
projects and pipeline routers are commented out. No static files mount.

## TASK: Implement all 5 files completely

### 1. backend/core/config.py
Replace with Pydantic v2 BaseModel approach:
- class ToolPaths(BaseModel): rc_exe_path, lfs_exe_path, ffmpeg_path, blender_exe_path, supersplat_url
- class StubConfig(BaseModel): ffmpeg_stub=False, rc_stub=True, lfs_stub=True, blender_stub=True,
  rc_stub_duration_seconds=8.0, lfs_stub_duration_seconds=15.0, lfs_stub_iterations=30000, lfs_stub_fake_ply=True
- class AppConfig(BaseModel): tools=ToolPaths(), stubs=StubConfig()
- load_config() → reads config.json, maps flat keys to nested AppConfig
- save_config(cfg: AppConfig) → writes flat JSON (backward compat with existing config.json)
- Singleton: app_config: AppConfig = load_config()
- config.json currently has flat keys: rc_exe_path, lfs_exe_path, etc. + stub keys. Keep backward compat.

### 2. backend/api/websocket.py
Implement:
- ConnectionManager class with active_connections: list[WebSocket], connect(), disconnect(), broadcast_json()
- manager = ConnectionManager() singleton
- @router.websocket("/ws/logs") endpoint: accept, add to manager, keep alive, remove on disconnect
- async def broadcast(step: str, level: str, message: str, progress: float | None = None, data: dict | None = None, file: str | None = None)
  Broadcasts JSON matching this TypeScript interface:
  { type: "log"|"progress"|"metric"|"status"|"file_ready", step, timestamp (ISO), level?, message?, progress?, data?, file? }
  Rules: if data → type="metric", if file → type="file_ready", if progress only → type="progress", else type="log"

### 3. backend/models/project.py
SQLModel complete schema:
- class Project(SQLModel, table=True):
  - id: Optional[str] = Field(default_factory=lambda: uuid4().hex[:8], primary_key=True)
  - name: str
  - slug: str (unique folder name)
  - created_at: datetime = Field(default_factory=datetime.utcnow)
  - updated_at: datetime = Field(default_factory=datetime.utcnow)
  - current_step: int = 0  (0=not started, 1-6=step number)
  - step_status: str = "{}"  (JSON string: {"1": "done", "2": "running", ...})
  - input_video_path: Optional[str] = None
  - frame_count: int = 0
  - settings_json: str = "{}"  (per-project settings overrides)
  - error_message: Optional[str] = None
- Helper methods (not table columns): get_step_status() -> dict, set_step_status(dict)

### 4. backend/db/database.py
- Keep engine creation with sqlite_url pointing to project root: Path(__file__).parents[2] / "pipeline.db"
- create_db_and_tables() unchanged
- Add get_session() generator for dependency injection

### 5. backend/main.py
- Import and include ALL 4 routers: projects, pipeline, settings, files (with correct prefixes /api/projects, /api/pipeline, /api/settings, /api/files)
- Call create_db_and_tables() on startup via @app.on_event("startup") or lifespan
- Mount static files: app.mount("/static", StaticFiles(directory=str(PROJECTS_DIR)), name="static")
  where PROJECTS_DIR = Path(__file__).parent.parent / "projects"
  Create the directory if not exists.
- Keep CORS middleware as-is

## CONSTRAINTS
- Use pathlib.Path throughout
- Python 3.11+, Pydantic v2 syntax (model_dump(), not dict())
- All imports must be correct relative imports (e.g. from backend.core.config import ...)
- Do not break the existing working settings API