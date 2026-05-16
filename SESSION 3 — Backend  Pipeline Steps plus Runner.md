## CONTEXT
Project: 3DGS Pipeline Web App — core pipeline execution
After Sessions 1+2: config, websocket, DB, models, routes all implemented.
broadcast() signature: async def broadcast(step, level, message, progress=None, data=None, file=None)
app_config singleton available from backend.core.config
PROJECTS_DIR = Path(__file__).parents[3] / "projects"

## TASK: Implement 6 step files + pipeline_runner.py

### 1. backend/core/steps/step_extract.py
Two functions: run_extract_real() and run_extract_stub() + dispatcher run_extract()

run_extract_real(project_path: Path, broadcast_fn, settings: dict):
  - FFmpeg command: ffmpeg -i {input_video} -vf "fps={fps},mpdecimate" -qscale:v {quality} frames/frame_%04d.jpg
  - settings keys: fps (default 2), quality (default 2), max_frames (default 0=unlimited), mpdecimate (default True)
  - input_video: first .mp4/.mov in project_path/input/
  - Use asyncio.create_subprocess_exec, stream stdout line by line
  - Parse FFmpeg output: detect "frame=" lines, extract frame number → broadcast progress
  - Timeout: 30min
  - On completion: return { frame_count: int, frames_dir: str }

run_extract_stub(project_path: Path, broadcast_fn, settings: dict):
  - Creates N minimal valid JPEG files (1×1 grey pixel, valid JPEG bytes: b'\xff\xd8\xff\xe0...')
  - n_frames = settings.get("max_frames", 60)
  - Simulate ~50ms per frame with asyncio.sleep(0.05)
  - Broadcast progress incrementally
  - Return same shape as real

### 2. backend/core/steps/step_rc.py
Implement EXACTLY the stub from the addendum prompt (8 phases: loading, feature detection, 
matching, bundle adjustment, export). Real runner calls RealityScan.exe -execrscmd.
Key: shutil.copy stub assets to rc_output/ at the end.
stub_assets path: Path(__file__).parents[4] / "tools" / "test_assets"

### 3. backend/core/steps/step_lfs.py
Implement EXACTLY the stub from the addendum prompt with realistic metrics simulation:
- Loss curve: starts ~0.15, decays exponentially toward ~0.02 with noise
- PSNR: starts ~18dB, grows toward ~28dB 
- Gaussians: grows from ~50k to ~300k
- Every ~500 sim iterations broadcast type="metric" with data={iteration, total_iterations, loss, psnr, num_gaussians, iter_per_sec}
- Real runner: LichtFeld-Studio.exe -d rc_output/ -o lfs_output/ -i {iterations} [--strategy mcmc]
- Parse real stdout with _parse_lfs_metrics() regex

### 4. backend/core/steps/step_export.py
run_export(project_path: Path, broadcast_fn, settings: dict):
  - Search lfs_output/ for .ply and .splat files
  - Copy to export/ dir
  - Broadcast file_ready for each file with absolute path
  - Set up watchdog FileSystemEventHandler to detect new .ply/.splat while LFS is running
  - Return { ply_path, splat_path (optional), export_dir }

### 5. backend/core/steps/step_blender.py
run_blender_real(project_path, broadcast_fn, settings):
  - Find .ply in export/
  - Call: blender --background --python backend/scripts/blender_splatforge.py -- --ply {ply} --out {export}/scene.blend
  - Stream stdout to broadcast
  - Write README_SPLATFORGE.txt in export/ explaining how to use scene.blend

run_blender_stub(project_path, broadcast_fn, settings):
  - Simulate 3 phases: "Loading scene...", "Importing PLY...", "Configuring SplatForge..."
  - Create a fake scene.blend file (just a text file with a note for stub)
  - Write README_SPLATFORGE.txt
  - Duration: 5 seconds

### 6. backend/core/pipeline_runner.py
Implement the full orchestrator:

PAUSE/ABORT mechanism:
  - Module-level: _abort_flags: dict[str, bool] = {}, _pause_events: dict[str, asyncio.Event] = {}
  - Functions: request_abort(project_id), request_pause(project_id), request_resume(project_id)
  - Each step checks abort flag between sub-operations

async def run_pipeline(project_id: str, start_from_step: int = 1, settings: dict = {}):
  1. Load project from DB (use direct SQLite, not FastAPI session)
  2. Get project_path from slug
  3. Initialize abort/pause events for project_id
  4. For each step in range(start_from_step, 7):
     a. Check abort flag → if set, update DB status=aborted, broadcast, return
     b. Wait on pause event (if paused)
     c. Update DB: current_step=step, step_status[step]="running"
     d. Broadcast status message: step starting
     e. Run the step function (extract/rc/lfs/export/blender based on step number)
     f. On success: update step_status[step]="done", broadcast SUCCESS
     g. On exception: update step_status[step]="error", error_message, broadcast ERROR, break
  5. On pipeline complete: broadcast final SUCCESS status
  6. Cleanup: remove abort/pause flags

STEP ROUTING:
  Step 1: already done by projects API (file copy happens at import)
  Step 2: step_extract.run_extract
  Step 3: step_rc.run_rc
  Step 4: step_lfs.run_lfs (then step_export.run_export automatically after LFS)
  Step 5: step_export.run_export (if not already done)
  Step 6: step_blender.run_blender

broadcast_fn passed to each step = partial(broadcast, step=step_name)

## CONSTRAINTS
- All subprocess calls: asyncio.create_subprocess_exec (never subprocess.run in async context)
- Timeout on all subprocess: asyncio.wait_for with 30min default
- Windows paths: use Path objects, convert with str() only at subprocess call time
- stub_assets: Path(__file__).parents[3] / "tools" / "test_assets"  ← verify relative depth
- Import app_config from backend.core.config (singleton), do NOT reload on each call