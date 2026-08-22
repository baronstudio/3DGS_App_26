## CONTEXT
Project: 3DGS Pipeline Web App — React + TypeScript
After Sessions 5-7: store, hooks, WizardShell, panels all implemented.
recharts must be installed: npm install recharts @types/recharts

## TASK: Implement all 6 step components

### components/wizard/steps/Step1_Import.tsx — Import
- Drag & drop zone (use HTML5 drag events or a thin wrapper, NO external DnD lib)
  Accept: .mp4, .mov, optional .srt
  Show file name + size after drop
- Project name input (text field)
  Auto-generate slug preview below: "folder: projects/my_video_2025/"
  Validation: required, min 3 chars
- "Start Import" button:
  POST /api/projects/create { name, settings: {} }
  Then: PUT /api/files/upload or handle via the project creation returning the project
  Note: actual file copy handled by backend. For now, show a path input as fallback.
  Set currentProjectId in store on success
- Display existing projects as small clickable chips to resume one
- After successful import: advance to step 2 (setCurrentStep(2) in store)

### components/wizard/steps/Step2_Extract.tsx — Frame Extraction
- Show current settings summary (fps, quality, mpdecimate)
- "Advanced Settings" button → opens FFmpegSettings in SettingsDrawer
- "Extract Frames" button → calls startPipeline(projectId, 2, ffmpegSettings)
- While running: show FrameGallery panel (live updating)
- ProgressBar component for "extract" step
- After completion: frame count badge, "Proceed to RS" button

### components/wizard/steps/Step3_RC.tsx — RealityScan Alignment
- Stub status banner (if rc_stub=true): orange banner "⚠ STUB MODE — RS simulated"
- "Advanced Settings" → RCSettings drawer
- "Run Alignment" button → startPipeline(projectId, 3, rcSettings)
- ProgressBar for "rc" step
- On completion: stats panel showing:
  "Aligned cameras: N" and "Sparse points: N"
  Parse from last SUCCESS log message (regex "Aligned X cameras, Y points")

### components/wizard/steps/Step4_LFS.tsx — LichtFeld Studio Training
- Stub status banner if lfs_stub=true
- "Advanced Settings" → LFSSettings drawer
- "Start Training" button → startPipeline(projectId, 4, lfsSettings)
- ProgressBar for "lfs" step with ETA
- Gaussian count badge (from lfsMetrics last entry)
- recharts LineChart (200px height):
  Two lines: Loss (left Y axis, 0-0.2) and PSNR (right Y axis, 15-32 dB)
  X axis: iterations
  Read from pipelineStore.lfsMetrics
  Update live as metrics arrive
  Colors: Loss=red, PSNR=cyan
- Control buttons row: [▶ Resume] [⏸ Pause] [⏹ Abort]
  Calls controlPipeline(projectId, action)
  Pause/Resume toggle based on pipelineRunning + a paused state

### components/wizard/steps/Step5_Export.tsx — Export & Launch
- Auto-runs after Step 4 completes (no manual trigger needed)
  But show a "Re-run Export Scan" button for manual trigger
- Display export files list (from pipelineStore.exportFiles or GET /api/files/{id}/export)
  Each file: icon + filename + size + action buttons
- For .ply file:
  "Open in SuperSplat" button → window.open(supersplatUrl + '?load=' + plyStaticUrl)
  "Download" button → <a download>
  "Copy path" button
- PlyViewer panel (iframe with SuperSplat)
- If no PLY yet: spinner + "Waiting for PLY output..."

### components/wizard/steps/Step6_Blender.tsx — Blender Scene (Optional)
- Show only if blender_exe_path is set in settings OR blender_stub=true
- If blender not detected AND not stub: grey out with message "Blender not detected. Configure path in Settings."
- "Generate Blender Scene" button → startPipeline(projectId, 6, {})
- ProgressBar for "blender" step
- On completion:
  Link to scene.blend file (download)
  Display README_SPLATFORGE.txt content in a code block
  Instructions: "Open scene.blend in Blender → Install SplatForge addon → splat object is pre-tagged"

## CONSTRAINTS
- recharts: import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
- All steps read/write pipelineStore via hooks, no local useState for pipeline state
- "Proceed" buttons only enabled when current step status === "done"  
- Each step shows its ProgressBar component only when status === "running" | "done"
- All API calls via hooks (usePipeline, useProjects), not direct fetch/axios in components