## CONTEXT
Project: 3DGS Pipeline Web App — final integration session
After Sessions 5-9: all components implemented. This session wires everything together.

## TASK: Final integration + polish

### 1. components/projects/ProjectList.tsx
- Read projects from pipelineStore
- Display as vertical list:
  Each project: name, created_at (relative: "2 days ago"), current step badge, status icon
  "Resume" button → selectProject(id) + setCurrentStep(project.current_step) + navigate to wizard
  "Delete" button with confirm dialog → deleteProject(id)
- "New Project" button → clears currentProjectId + setCurrentStep(1)
- Empty state: "No projects yet. Start by importing a video."
- Show in SetupScreen AND accessible from WizardShell top bar via a projects dropdown

### 2. App.tsx — full routing logic
- useWebSocket() initialized once at App level
- Show SetupScreen on first launch (no projects in DB AND stubs not explicitly disabled)
- After "Proceed" click OR if projects exist → show MainPage (WizardShell)
- Persist "proceeded" state in localStorage (key: "3dgs_proceeded")

### 3. config.json — fix stub defaults
Change rc_stub, lfs_stub, blender_stub to true (development defaults per addendum prompt):
  "rc_stub": true, "lfs_stub": true, "blender_stub": true

### 4. components/pipeline/LogViewer.tsx (used in old MainPage — keep for compat)
Replace with a redirect to LiveLog panel or just re-export LiveLog

### 5. Install missing npm dependency
Run: npm install recharts
Verify: import works in Step4_LFS.tsx

### 6. End-to-end stub test
1. Start backend: uvicorn backend.main:app --reload (from 3dgs-pipeline-app, venv activated)
2. Start frontend: npm run dev (from frontend/)
3. Open http://localhost:5173
4. Verify SetupScreen shows with stub status table
5. Click Proceed → WizardShell opens
6. Step 1: enter project name, create project → verify folder created in projects/
7. Step 2: click Extract → verify stub creates N jpg files in projects/{slug}/frames/
8. Step 3: click RC Alignment → verify stub runs, logs stream to LiveLog
9. Step 4: click LFS Training → verify metrics update in chart
10. Step 5: verify PLY appears in export list
11. Fix any errors found

### 7. README.md — add "Development without hardware" section
Per addendum prompt section §11:
- What stubs do
- How to disable stubs (production mode, steps to follow)
- Adjusting stub duration in Settings

## KNOWN ISSUES TO WATCH FOR
- pipelineStore.ts: 'zustand v4 — use import { create } from "zustand"' (not default import)
- backend static files: ensure PROJECTS_DIR exists before mounting StaticFiles
- WebSocket reconnection: if backend restarts, frontend WS should reconnect automatically
- Windows paths in JSON responses: use .as_posix() to avoid double-backslash issues