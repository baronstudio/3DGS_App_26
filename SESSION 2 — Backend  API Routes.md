## CONTEXT
Project: 3DGS Pipeline Web App — backend API routes
After Session 1: config.py has AppConfig/StubConfig Pydantic models, 
websocket.py has broadcast() function, models/project.py has full Project SQLModel,
db/database.py has get_session(), main.py mounts all routers.

## CURRENT STATE (all stubs to replace completely)

### backend/api/routes/projects.py — returns hardcoded empty responses
### backend/api/routes/pipeline.py — returns hardcoded strings
### backend/api/routes/files.py — returns empty lists

## TASK: Implement all 3 route files

### 1. backend/api/routes/projects.py
Implement full CRUD using SQLModel + Session:

POST /create  body: { name: str, settings?: dict }
  - Slug = re.sub(r'[^a-z0-9_-]', '_', name.lower())
  - Create project folder: projects/{slug}/input/, frames/, rc_output/, lfs_output/, export/
  - Save Project to DB, return full project dict
  
GET /  → list all projects ordered by created_at DESC, return list of project dicts

GET /{id}  → return project dict + computed paths:
  { ...project, paths: { input, frames, rc_output, lfs_output, export } }

DELETE /{id}
  - Delete project folder (shutil.rmtree) 
  - Delete from DB
  - Return { deleted: id }

PUT /{id}  body: partial update dict
  - Allowed fields: name, current_step, step_status (as dict → json), settings_json (as dict → json), error_message
  - Update updated_at
  - Return updated project

Helper: get_project_path(slug: str) → Path("projects") / slug

### 2. backend/api/routes/pipeline.py
This is the async pipeline control layer. The actual execution lives in pipeline_runner.py (not yet implemented — use a placeholder import for now).

POST /start  body: { project_id: str, start_from_step: int = 1, settings: dict = {} }
  - Load project from DB (404 if not found)
  - If pipeline already running for this project → return 409
  - Launch asyncio.create_task(run_pipeline(project_id, start_from_step, settings))
  - Store task reference in a module-level dict: _running_tasks: dict[str, asyncio.Task]
  - Return { status: "started", project_id, step: start_from_step }

POST /control  body: { project_id: str, action: "pause" | "resume" | "abort" }
  - abort: cancel the task in _running_tasks, broadcast status=aborted
  - pause/resume: set a flag in a module-level dict _pause_events: dict[str, asyncio.Event]
  - Return { status: action, project_id }

GET /status  query: project_id (optional)
  - If project_id given: return { project_id, running: bool, current_step, step_status }
  - Else: return all running tasks as list

### 3. backend/api/routes/files.py
Use pathlib for all file ops. PROJECTS_DIR = Path(__file__).parents[3] / "projects"

GET /{project_id}/frames
  - List all .jpg/.jpeg/.png in projects/{slug}/frames/
  - For each file: { filename, path (relative), size_bytes, url: /static/{slug}/frames/{filename} }
  - Sort by filename
  - Flag bottom 5% by file size as blurry: { ..., potentially_blurry: true }
  - Return { frames: [...], total: int, blurry_count: int }

DELETE /{project_id}/frames  body: { filenames: list[str] }
  - Delete listed files from frames/ dir
  - Return { deleted: int, remaining: int }

GET /{project_id}/export
  - List files in projects/{slug}/export/ (any extension)
  - For each: { filename, size_bytes, url: /static/{slug}/export/{filename} }
  - Return { files: [...] }

Helper: get_slug_from_id(project_id, session) → query DB for project slug

## CONSTRAINTS
- Use Depends(get_session) from db/database.py for all DB operations
- Use async def for all endpoints that do file I/O
- Import broadcast from backend.api.websocket for any status updates
- All paths via pathlib.Path, normalize with .as_posix() for JSON responses
- Handle FileNotFoundError gracefully (404), return meaningful error messages