---
name: run-3dgs-app
description: Launch, stop, or verify the 3DGS Pipeline web app (FastAPI backend + Vite/React frontend). Use when asked to run/start/restart the app, check that the servers are up, reproduce a bug in the real UI, or take a screenshot of the running app.
---

# Run the 3DGS Pipeline app

Two servers must run together. All paths are relative to `3dgs-pipeline-app/`.

| Part | Command | URL |
|---|---|---|
| Backend | `.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload` | http://127.0.0.1:8000 |
| Frontend | `npm run dev` in `frontend/` | http://localhost:5173 |

Vite proxies `/api`, `/static` and `/ws` to port 8000, so **always open the frontend URL (5173), never 8000**.

## Preferred way - the launcher script

```powershell
cd g:\travail\DEV\3DGS_App_26\3dgs-pipeline-app
.\start.bat
```

`start.bat` opens two separate console windows (Backend / Frontend). The browser auto-open lines are commented out - open http://localhost:5173 yourself.

On Linux/macOS the equivalent is `./start.sh`.

## Manual way - two terminals

Terminal 1 (backend) - **call the venv interpreter directly, never activate** (see the gotcha below):
```powershell
cd g:\travail\DEV\3DGS_App_26\3dgs-pipeline-app
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 2 (frontend):
```powershell
cd g:\travail\DEV\3DGS_App_26\3dgs-pipeline-app\frontend
npm run dev
```

When starting these from a tool call, use `run_in_background: true` for both - they are long-running watchers that never exit on their own.

## Gotcha - `ModuleNotFoundError: No module named 'sqlmodel'`

Means the backend booted under **global** Python instead of the venv. Confirm from the traceback paths: `C:\Users\jbbar\AppData\Local\Programs\Python\Python311\Lib\site-packages\...` is the global install; the venv would read `...\3dgs-pipeline-app\.venv\...`.

Root cause: `.venv/Scripts/activate.bat` hardcodes `VIRTUAL_ENV=C:\Travail\DEV\3DGS_App_26\...` from when the project lived on the C: drive. The project is now on G:, so activation prepends a nonexistent directory to PATH and `uvicorn` resolves to the global install. `Activate.ps1` derives its path at runtime and is NOT affected - only the `.bat` path is broken.

Fix: skip activation entirely and invoke `.\.venv\Scripts\python.exe -m uvicorn ...` (this is what the patched `start.bat` does). Same rule for pip: `.\.venv\Scripts\python.exe -m pip install ...`.

Version note: the venv is Python 3.14 (`home = C:\Python314`); bare `python` on PATH is 3.11. Regenerating the venv (`python setup.py`) would also fix the stale path, but changes the interpreter version - patching is safer.

## First-time / after dependency changes

```powershell
cd g:\travail\DEV\3DGS_App_26\3dgs-pipeline-app
python setup.py            # creates .venv, installs backend deps, clones tools
cd frontend && npm install
```

`setup.py` also auto-detects tool paths and writes `config.json`. Both `.venv/` and `frontend/node_modules/` already exist in this checkout, so setup is normally not needed.

## Verifying it's up

- Backend: `curl http://127.0.0.1:8000/docs` (FastAPI auto-docs) or hit an `/api/...` route.
- Import-only smoke test, no server: `.\.venv\Scripts\python.exe -c "from backend.main import app"`.
- Frontend: Vite prints `Local: http://localhost:5173/`.
- Port already in use -> a previous run is still alive. Find it with
  `Get-NetTCPConnection -LocalPort 8000,5173 -State Listen | Select-Object LocalPort,OwningProcess`
  then `Stop-Process -Id <pid>`.

## Build / lint (frontend)

```powershell
cd g:\travail\DEV\3DGS_App_26\3dgs-pipeline-app\frontend
npm run build     # tsc + vite build
npm run lint      # eslint, --max-warnings 0
```
