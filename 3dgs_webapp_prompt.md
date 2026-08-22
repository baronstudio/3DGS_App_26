# AGENT PROMPT — 3DGS Pipeline Web App (Local)
## For: GitHub Copilot Agent / Claude Code / VS Code

---

## CONTEXT & MISSION

Build a **local web application** that orchestrates a full **3D Gaussian Splatting production pipeline** from a DJI Action Cam 4K MP4 video to a final `.ply` / `.splat` file, auto-opened in SuperSplat.

The stack is based on:
- **RealityScan** — camera alignment via CLI (`.bat` / `.rscmd` scripts)
- **LichtFeld Studio** — 3DGS training via CLI headless mode
- **FFmpeg** — video frame extraction
- **SuperSplat** — final viewer, auto-launched at end of pipeline
- **Blender + SplatForge** — optional `.blend` scene export for relighting

The app runs **100% locally** on Windows (primary target), with a local web server via **Vite**.
All processing happens on the user's machine — no cloud, no external API.

---

## TECHNICAL STACK

| Layer | Technology |
|---|---|
| Frontend | **React 18** + **TypeScript** |
| Dev server / bundler | **Vite 5** |
| UI components | **shadcn/ui** (Radix UI primitives) + **Tailwind CSS v4** |
| State management | **Zustand** |
| Backend / orchestration | **Python 3.11+** via **FastAPI** (local REST API + WebSocket for live logs) |
| CMS / config | **JSON-based project config** managed via **Pydantic** models + **SQLite** (via SQLModel) for project history |
| Python env | **`.venv`** created at project root with `python -m venv .venv` |
| Process execution | Python `subprocess` + `asyncio` for non-blocking pipeline execution |
| File watch | **watchdog** (Python) for output file detection |
| Auto-launch | `webbrowser` module (Python) for SuperSplat, `subprocess` for Blender |
| Repo dependencies | Auto-cloned via Python `subprocess` calling `git clone` at first run |

---

## PROJECT STRUCTURE TO GENERATE

```
3dgs-pipeline-app/
├── .venv/                          # Python virtual environment (auto-created)
├── frontend/                       # Vite + React app
│   ├── src/
│   │   ├── components/
│   │   │   ├── wizard/
│   │   │   │   ├── WizardShell.tsx         # Main wizard container
│   │   │   │   ├── steps/
│   │   │   │   │   ├── Step1_Import.tsx    # Video + data import
│   │   │   │   │   ├── Step2_Extract.tsx   # FFmpeg frame extraction
│   │   │   │   │   ├── Step3_RC.tsx        # RealityScan alignment
│   │   │   │   │   ├── Step4_LFS.tsx       # LichtFeld Studio training
│   │   │   │   │   ├── Step5_Export.tsx    # PLY / splat export + SuperSplat
│   │   │   │   │   └── Step6_Blender.tsx   # Optional Blender/SplatForge scene
│   │   │   │   └── StepNav.tsx             # Sidebar step navigator
│   │   │   ├── panels/
│   │   │   │   ├── LiveLog.tsx             # Real-time WebSocket log terminal
│   │   │   │   ├── ProgressBar.tsx         # Per-step progress with ETA
│   │   │   │   ├── FrameGallery.tsx        # Extracted frames preview grid
│   │   │   │   └── PlyViewer.tsx           # Embedded SuperSplat iframe or PLY preview
│   │   │   ├── settings/
│   │   │   │   ├── SettingsDrawer.tsx      # Advanced settings panel (collapsible)
│   │   │   │   ├── FFmpegSettings.tsx      # FPS, quality, mpdecimate toggle
│   │   │   │   ├── RCSettings.tsx          # RS alignment params, component filter
│   │   │   │   └── LFSSettings.tsx         # Iterations, MCMC/default, learning rate, etc.
│   │   │   └── ui/                         # shadcn/ui auto-generated components
│   │   ├── store/
│   │   │   └── pipelineStore.ts            # Zustand global state
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts             # WS connection to backend
│   │   │   └── usePipeline.ts              # Pipeline control (start/pause/abort)
│   │   ├── api/
│   │   │   └── client.ts                   # Axios REST client to FastAPI
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── package.json
├── backend/                        # Python FastAPI
│   ├── main.py                     # FastAPI app entrypoint
│   ├── api/
│   │   ├── routes/
│   │   │   ├── projects.py         # CRUD project management
│   │   │   ├── pipeline.py         # Pipeline control endpoints
│   │   │   ├── settings.py         # Read/write settings
│   │   │   └── files.py            # File browser, PLY download
│   │   └── websocket.py            # WS log streaming
│   ├── core/
│   │   ├── pipeline_runner.py      # Orchestrates all steps sequentially
│   │   ├── steps/
│   │   │   ├── step_extract.py     # FFmpeg frame extraction
│   │   │   ├── step_rc.py          # RealityScan CLI execution
│   │   │   ├── step_lfs.py         # LichtFeld Studio CLI execution
│   │   │   ├── step_export.py      # PLY/splat file detection + copy
│   │   │   └── step_blender.py     # Blender headless scene generation
│   │   ├── dep_manager.py          # Git clone / check dependencies
│   │   └── config.py               # App-wide paths, tool paths
│   ├── models/
│   │   ├── project.py              # SQLModel project schema
│   │   └── settings.py             # Pydantic settings schemas
│   ├── db/
│   │   └── database.py             # SQLite init via SQLModel
│   ├── scripts/
│   │   ├── rc_align_export.rscmd   # RealityScan .rscmd script template
│   │   └── blender_splatforge.py   # Blender Python script for SplatForge scene
│   └── requirements.txt
├── tools/                          # Auto-cloned external tools (git clone targets)
│   ├── lichtfeld-studio/           # MrNeRF/LichtFeld-Studio
│   ├── supersplat/                 # playcanvas/supersplat (local fallback)
│   └── colmap/                     # fallback if RS not found
├── projects/                       # User projects (created at runtime)
│   └── [project_name]/
│       ├── input/                  # Original MP4 + DJI data files
│       ├── frames/                 # FFmpeg extracted frames
│       ├── rc_output/              # RS registration CSV + sparse PLY
│       ├── lfs_output/             # LichtFeld Studio trained output
│       └── export/                 # Final PLY, SPLAT, .blend scene
├── setup.py                        # First-run setup: .venv, pip install, git clones
├── start.bat                       # Windows launcher (venv activate + uvicorn + vite)
├── start.sh                        # Linux/macOS launcher
└── README.md
```

---

## SETUP SCRIPT (`setup.py`)

Write a `setup.py` that:
1. Checks Python version (≥ 3.11)
2. Creates `.venv` at project root: `python -m venv .venv`
3. Installs Python deps from `backend/requirements.txt` into `.venv`
4. Runs `npm install` in `frontend/`
5. Auto-clones these repos into `tools/` if not already present:
   - `git clone https://github.com/MrNeRF/LichtFeld-Studio tools/lichtfeld-studio`
   - `git clone https://github.com/playcanvas/supersplat tools/supersplat`
6. Writes a `config.json` at root storing:
   - `rc_exe_path`: auto-detected path to `RealityScan.exe` (search in `C:/Program Files/Epic Games/`)
   - `lfs_exe_path`: built LichtFeld Studio binary path
   - `ffmpeg_path`: auto-detected `ffmpeg` in PATH or bundled
   - `blender_exe_path`: auto-detected `blender.exe`
   - `supersplat_url`: `https://superspl.at/editor` (default online) or local build

---

## BACKEND (`backend/requirements.txt`)

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
websockets>=12.0
pydantic>=2.7.0
sqlmodel>=0.0.18
watchdog>=4.0.0
aiofiles>=23.2.0
python-multipart>=0.0.9
httpx>=0.27.0
```

---

## PIPELINE STEPS — DETAILED SPECIFICATION

### STEP 1 — Import
- Drag & drop or file picker for:
  - `.mp4` / `.mov` video file (DJI 4K)
  - Optional: DJI `.SRT` sidecar file
  - Optional: any extra data files (GPS, IMU)
- Project name input (auto-slugified for folder name)
- Files copied to `projects/[name]/input/`

### STEP 2 — Frame Extraction (FFmpeg)
**Default settings (wizard mode):**
```bash
ffmpeg -i input.mp4 -vf "fps=2,mpdecimate" -qscale:v 2 frames/frame_%04d.jpg
```
**Advanced settings (drawer):**
- FPS selector: 0.5 / 1 / 2 / 3 / 5 (radio)
- `mpdecimate` toggle (on by default)
- JPEG quality: slider 1–5 (`-qscale:v`)
- Max frames cap (auto-stop after N frames)
- Frame preview gallery (thumbnail grid, 5 columns) updated live during extraction
- Manual frame deletion (checkbox + bulk delete) before proceeding
- Frame count badge + estimated VRAM requirement display

### STEP 3 — RealityScan Alignment (CLI)
**Wizard mode:**
Run the following RS CLI sequence via a generated `.bat` / `.rscmd`:
```bat
RealityScan.exe ^
  -addFolder "projects/[name]/frames/" ^
  -align ^
  -exportRegistration "projects/[name]/rc_output/registration.csv" "scripts/rc_reg_params.xml" ^
  -exportSparsePointCloud "projects/[name]/rc_output/pointcloud.ply" "scripts/rc_ply_params.xml" ^
  -quit
```
**Advanced settings (drawer):**
- Alignment precision: Preview / Normal / High (maps to RS `-setAlignmentPreset`)
- Max features per image: slider 40000–80000
- Component filter: keep largest only (toggle, maps to `-selectMaximalComponent`)
- Custom reconstruction region: import `.rsbox` file
- Export format fallback: COLMAP Text if RS not found

**Live display:**
- RS process stdout/stderr streamed to `LiveLog` panel via WebSocket
- Parsed progress: detect "Aligned X cameras" lines and update progress bar
- On completion: show sparse point cloud stats (camera count, point count)
- Fallback alert if RS not found: propose COLMAP instead

### STEP 4 — LichtFeld Studio Training (CLI headless)
**Wizard mode:**
```bash
LichtFeld-Studio.exe \
  -d projects/[name]/rc_output/ \
  -o projects/[name]/lfs_output/ \
  -i 30000
```
**Advanced settings (drawer):**
- Iterations: slider 5000–100000 (default 30000)
- Strategy: Default / MCMC (maps to `--strategy mcmc`)
- Learning rate: float input (default 0.001)
- Save interval: every N iterations (checkpoint)
- Render mode: RGB / RGB_D / DEPTH
- Eval mode toggle (`--eval`)
- `--save-eval-images` toggle
- Background color: color picker

**Live display:**
- Parse LFS stdout for: `iteration`, `loss`, `PSNR`, `num_gaussians`
- Live chart: loss curve + PSNR over iterations (recharts LineChart)
- Gaussian count display (badge, updates every 1000 iter)
- ETA estimation from iteration speed (iter/s → remaining time)
- Pause / Resume / Abort controls calling backend `/pipeline/control` endpoint

### STEP 5 — Export & Launch
**Outputs detected in `lfs_output/`:**
- `.ply` file (standard Gaussian Splat)
- `.splat` file (compressed, if generated)
- Copied to `projects/[name]/export/`

**Actions:**
- "Open in SuperSplat" button → open `https://superspl.at/editor` in default browser with PLY path hint (or serve PLY locally via FastAPI static endpoint and pass URL param)
- Download PLY button → direct file link
- Copy output folder path button
- Optional: open in local SuperSplat build if `tools/supersplat/` exists

### STEP 6 — Blender / SplatForge Scene (Optional)
Only shown if Blender is detected in `config.json`.

**What it generates:**
Run `blender --background --python backend/scripts/blender_splatforge.py -- --ply projects/[name]/export/output.ply --out projects/[name]/export/scene.blend`

The Python script (`blender_splatforge.py`) must:
1. Import the `.ply` as a point cloud object (Blender's built-in point cloud or via bpy mesh import)
2. Set up a basic scene: HDRI world shader (solid neutral grey, easily replaceable), one area light, camera at orbital position
3. Add a comment/custom property on the point cloud object: `"splatforge_ready": True` and `"ply_source": "[path]"` — SplatForge addon will detect this
4. Set render engine to EEVEE Next
5. Save as `scene.blend` with all paths relative
6. Add a README note in the export folder: "Open scene.blend in Blender, install SplatForge addon, the splat object is pre-configured."

---

## UI/UX SPECIFICATION

### Wizard Shell
- Left sidebar: vertical step navigator
  - Each step: icon + label + status badge (pending / running / done / error)
  - Steps clickable only if previous step completed (or bypass toggle in dev mode)
- Main area: current step content
- Right panel (collapsible): `LiveLog` terminal — dark background, monospace font, auto-scroll, color-coded by log level (INFO=white, WARNING=yellow, ERROR=red, SUCCESS=green)
- Top bar: project name + current step + global abort button

### Settings Drawer
- Triggered by "Advanced Settings" button on each step
- Slides in from right (shadcn Sheet component)
- Each tool's settings isolated per step
- "Reset to defaults" button per section
- Settings persisted per project in SQLite

### Visual style
- Dark theme (slate-900 background)
- Accent color: electric cyan (`#00D4FF`) for active states and progress
- Monospace font for log terminal and file paths (JetBrains Mono or similar)
- Clean, utilitarian aesthetic — no decorative chrome
- Step completion: green checkmark animation
- Error state: red border + inline error message with suggested fix

---

## WEBSOCKET PROTOCOL

Backend broadcasts to frontend via WS at `ws://localhost:8000/ws/logs`:

```typescript
// Message format
interface WsMessage {
  type: "log" | "progress" | "metric" | "status" | "file_ready";
  step: "extract" | "rc" | "lfs" | "export" | "blender";
  timestamp: string;       // ISO
  level?: "INFO" | "WARNING" | "ERROR" | "SUCCESS";
  message?: string;        // Raw log line
  progress?: number;       // 0.0 – 1.0
  data?: {                 // For "metric" type
    iteration?: number;
    loss?: number;
    psnr?: number;
    num_gaussians?: number;
    fps?: number;
  };
  file?: string;           // For "file_ready" type: absolute path to output file
}
```

---

## REST API ENDPOINTS

```
POST   /api/projects/create          # Create new project
GET    /api/projects/                # List all projects
GET    /api/projects/{id}            # Get project details + step states
DELETE /api/projects/{id}            # Delete project + files

POST   /api/pipeline/start           # Start pipeline from a given step
POST   /api/pipeline/control         # {"action": "pause"|"resume"|"abort"}
GET    /api/pipeline/status          # Current step + overall status

GET    /api/settings/                # Read global settings (tool paths)
PUT    /api/settings/                # Update tool paths

GET    /api/files/{project_id}/frames # List extracted frames (thumbnails)
DELETE /api/files/{project_id}/frames # Delete selected frames
GET    /api/files/{project_id}/export # List export files (PLY, SPLAT, blend)

GET    /static/projects/{project_id}/export/{filename}  # Serve PLY for SuperSplat
```

---

## DEPENDENCY AUTO-CLONE LOGIC (`dep_manager.py`)

```python
DEPENDENCIES = [
    {
        "name": "LichtFeld Studio",
        "repo": "https://github.com/MrNeRF/LichtFeld-Studio",
        "local_path": "tools/lichtfeld-studio",
        "check_file": "README.md",
        "post_clone": None  # User must build manually; show build instructions in UI
    },
    {
        "name": "SuperSplat (local fallback)",
        "repo": "https://github.com/playcanvas/supersplat",
        "local_path": "tools/supersplat",
        "check_file": "package.json",
        "post_clone": "npm install"  # Run in tools/supersplat/
    }
]
```

On first run, the UI shows a "Setup" screen before the wizard:
- Checklist of all dependencies
- Green/red status per tool (detected / missing)
- "Auto-install missing" button → triggers dep_manager
- Manual path override for RS, LFS, Blender, FFmpeg
- "Proceed to pipeline" button (enabled when RS + LFS + FFmpeg are resolved)

---

## LAUNCHER SCRIPTS

### `start.bat` (Windows)
```bat
@echo off
cd /d %~dp0
call .venv\Scripts\activate
start "" uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
cd frontend
start "" npm run dev
timeout /t 3
start http://localhost:5173
```

### `start.sh` (Linux/macOS)
```bash
#!/bin/bash
source .venv/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload &
cd frontend && npm run dev &
sleep 3
xdg-open http://localhost:5173 2>/dev/null || open http://localhost:5173
```

---

## RS CLI SCRIPT TEMPLATE (`rc_align_export.rscmd`)

```
-addFolder "$(arg0)"
-align
-selectMaximalComponent
-exportRegistration "$(arg1)/registration.csv" "$(arg2)/rc_reg_params.xml"
-exportSparsePointCloud "$(arg1)/pointcloud.ply" "$(arg2)/rc_ply_params.xml"
-quit
```

The Python step (`step_rc.py`) generates the `.xml` parameter files for registration and PLY export using RS's documented XML schema, then calls:
```bat
RealityScan.exe -execrscmd rc_align_export.rscmd "frames_path" "rc_output_path" "scripts_path"
```

---

## BLENDER SCRIPT TEMPLATE (`blender_splatforge.py`)

```python
"""
Blender headless script — SplatForge-ready scene setup.
Usage: blender --background --python blender_splatforge.py -- --ply /path/to/output.ply --out /path/to/scene.blend
"""
import bpy
import sys
import argparse
import os

# Parse custom args after '--'
argv = sys.argv[sys.argv.index("--") + 1:]
parser = argparse.ArgumentParser()
parser.add_argument("--ply", required=True, help="Path to the .ply splat file")
parser.add_argument("--out", required=True, help="Output .blend path")
args = parser.parse_args(argv)

# Clean default scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import PLY as mesh (SplatForge will re-interpret it)
bpy.ops.wm.ply_import(filepath=args.ply)
splat_obj = bpy.context.selected_objects[0]
splat_obj.name = "GaussianSplat"

# Tag for SplatForge detection
splat_obj["splatforge_ready"] = True
splat_obj["ply_source"] = args.ply
splat_obj["pipeline_tool"] = "3dgs-pipeline-app"

# Basic scene setup
# World shader — neutral grey HDRI-ready
world = bpy.context.scene.world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.05, 0.05, 0.05, 1.0)
bg.inputs[1].default_value = 1.0

# Area light
bpy.ops.object.light_add(type='AREA', location=(3, -3, 5))
light = bpy.context.active_object
light.data.energy = 500
light.data.size = 2.0

# Camera — orbital position facing scene center
bpy.ops.object.camera_add(location=(4, -4, 3))
cam = bpy.context.active_object
cam.data.lens = 35
# Point camera at origin
import mathutils
direction = mathutils.Vector((0, 0, 0)) - cam.location
rot_quat = direction.to_track_quat('-Z', 'Y')
cam.rotation_euler = rot_quat.to_euler()
bpy.context.scene.camera = cam

# Render settings — EEVEE Next
bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT'
bpy.context.scene.render.resolution_x = 1920
bpy.context.scene.render.resolution_y = 1080

# Save
bpy.ops.wm.save_as_mainfile(filepath=args.out)
print(f"[3DGS Pipeline] Scene saved: {args.out}")
print("[3DGS Pipeline] Open in Blender and install SplatForge addon to begin relighting.")
```

---

## ADDITIONAL REQUIREMENTS

1. **Error handling**: Every subprocess call must have timeout, stderr capture, and meaningful error messages surfaced to the UI (not just "process failed").

2. **Project persistence**: Each pipeline run is saved as a project in SQLite. User can re-open a past project and resume from any completed step.

3. **Config validation**: On startup, validate all tool paths exist. Show non-blocking warnings in the UI for missing optional tools (Blender).

4. **Frame quality filter**: After extraction, auto-sort frames by file size and flag the smallest 5% as "potentially blurry" with a visual indicator in the gallery.

5. **PLY file watcher**: After LFS training starts, use `watchdog` to monitor `lfs_output/` and update the UI as soon as a `.ply` or checkpoint file appears.

6. **SuperSplat integration**: Serve the output PLY via FastAPI static route. The "Open in SuperSplat" button constructs: `https://superspl.at/editor?load=http://localhost:8000/static/projects/{id}/export/output.ply` and opens it in the default browser via `webbrowser.open()`.

7. **README.md**: Generate a full README with:
   - Prerequisites (NVIDIA GPU, CUDA 12.8+, Python 3.11+, Node 20+, RS installed via Epic Games Launcher, FFmpeg in PATH)
   - Quick start: `python setup.py && start.bat`
   - Tool path configuration
   - Pipeline walkthrough with screenshots placeholders
   - LichtFeld Studio build instructions (link to official wiki)
   - SplatForge usage instructions for the generated `.blend`

---

## IMPORTANT NOTES FOR THE AGENT

- **Do not hallucinate tool CLIs.** Use only documented RS CLI commands from `rshelp.capturingreality.com`. The key commands are: `-addFolder`, `-align`, `-selectMaximalComponent`, `-exportRegistration`, `-exportSparsePointCloud`, `-quit`, `-execrscmd`.
- **LichtFeld Studio CLI**: The documented headless syntax is `LichtFeld-Studio.exe -d <colmap_dataset_path> -o <output_path> -i <iterations>`. Additional flags: `--strategy mcmc`, `--eval`, `--save-eval-images`, `--render-mode RGB_D`. Source: [LichtFeld Studio Wiki](https://github.com/MrNeRF/LichtFeld-Studio/wiki).
- **FFmpeg frame extraction**: Use `-vf "fps=2,mpdecimate" -qscale:v 2` as default. The `mpdecimate` filter requires FFmpeg compiled with it (standard builds include it).
- **Python subprocess**: Use `asyncio.create_subprocess_exec()` for non-blocking execution. Stream stdout line by line via `async for line in process.stdout`.
- **COLMAP format**: LichtFeld Studio expects COLMAP format input (images + sparse/0/ with cameras.bin, images.bin, points3D.bin). RealityScan exports to COLMAP format via `-exportColmap` command — use this instead of the CSV/PLY approach if the LFS version requires strict COLMAP format. Implement both paths with auto-detection.
- **`.venv` activation in subprocess**: When calling Python scripts from within the app, always use the `.venv` Python interpreter explicitly: `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (Linux).
- The user is on **Windows** as primary platform. All path separators must handle both `\\` and `/`. Use `pathlib.Path` throughout.
- **Do not install or recommend Postshot** — the user has explicitly chosen LichtFeld Studio.
