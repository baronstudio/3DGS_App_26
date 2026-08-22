## CONTEXT
Project: 3DGS Pipeline Web App
After Sessions 1-3: full backend implemented.

## TASK: Implement dep_manager.py + generate sample.ply

### 1. backend/core/dep_manager.py
Implement tool detection and dependency status:

TOOLS_TO_CHECK = [
  { id: "ffmpeg", name: "FFmpeg", detect: "ffmpeg -version" in PATH or check config.tools.ffmpeg_path },
  { id: "rc", name: "RealityScan", detect: check config.tools.rc_exe_path exists },
  { id: "lfs", name: "LichtFeld Studio", detect: check config.tools.lfs_exe_path exists },
  { id: "blender", name: "Blender", detect: check config.tools.blender_exe_path exists }
]

Functions:
- check_all_tools() → dict[str, bool]  (runs all checks, returns {tool_id: found})
- auto_detect_rc() → Optional[str]  (search C:/Program Files/Epic Games/**/RealityScan.exe)
- auto_detect_blender() → Optional[str]  (search C:/Program Files/Blender Foundation/**/blender.exe)
- auto_detect_ffmpeg() → Optional[str]  (shutil.which("ffmpeg"))
- get_tool_status() → list of { id, name, found: bool, path: str|None, stub_active: bool }

### 2. tools/test_assets/generate_sample_ply.py
Complete the script from the addendum prompt:
- Generate N=500 Gaussians with random positions in a 2m sphere
- All required 3DGS PLY properties: x,y,z,nx,ny,nz,f_dc_0,f_dc_1,f_dc_2,
  f_rest_0,f_rest_1,f_rest_2,opacity,scale_0,scale_1,scale_2,rot_0,rot_1,rot_2,rot_3
- Binary little-endian format
- Output: tools/test_assets/sample.ply
- Also copy sample.ply to stub_pointcloud.ply in same dir

Then RUN the script to generate the actual file:
  cd c:\Travail\DEV\3DGS_App_26\3dgs-pipeline-app
  .venv\Scripts\python.exe tools/test_assets/generate_sample_ply.py

Verify output: sample.ply should exist and be ~50-80KB.

### 3. Verify backend starts correctly
Run: uvicorn backend.main:app --reload (from 3dgs-pipeline-app dir, venv activated)
Check: GET /api/settings/ returns the config, GET /api/projects/ returns []
Fix any import errors found.