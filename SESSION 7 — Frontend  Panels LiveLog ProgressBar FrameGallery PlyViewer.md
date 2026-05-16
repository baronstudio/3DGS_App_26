## CONTEXT
Project: 3DGS Pipeline Web App — React + TypeScript
After Session 6: WizardShell + StepNav implemented.
All panels are currently stubs: <div>Live Log</div> etc.

## TASK: Implement all 4 panel components

### 1. components/panels/LiveLog.tsx
Real-time WebSocket log terminal:
- Read logs from pipelineStore (logs: LogEntry[])
- Display in a dark terminal-style container:
  font-family: JetBrains Mono or monospace fallback
  bg-slate-950, text-sm, p-3, rounded
  max-height: 100%, overflow-y: auto
- Auto-scroll to bottom on new logs (useEffect on logs.length)
  But: stop auto-scrolling if user has scrolled up (detect scroll position)
- Color coding:
  INFO → text-slate-300
  WARNING → text-yellow-400
  ERROR → text-red-400
  SUCCESS → text-green-400
- Each line: [HH:MM:SS] [STEP] MESSAGE
- "Clear" button top-right (calls clearLogs from store)
- Line count badge
- Props: className?: string (for sizing in WizardShell)

### 2. components/panels/ProgressBar.tsx
Per-step progress indicator:
- Props: step: string, label: string
- Read progress from pipelineStore.stepProgress[step]
- Visual: 
  - Label left, percentage right
  - Animated progress bar (transition-all duration-300)
  - Active: bg-cyan-500, bg-cyan-500/20 track
  - Done: bg-green-500
  - Error: bg-red-500
- ETA display: 
  - Track progress over time (store start timestamp + progress samples)
  - Estimate remaining time as: elapsed / progress * (1 - progress)
  - Display "~Xm Ys remaining" or "Almost done..."
  - Only show when progress > 0.05 and < 0.99

### 3. components/panels/FrameGallery.tsx
Extracted frames preview grid:
- Props: projectId: string, onDelete?: (filenames: string[]) => void
- Fetch frames list from GET /api/files/{projectId}/frames
- Refresh every 2s while extraction is running (check pipelineStore.stepStatuses[2])
- Display as CSS grid, 5 columns on desktop
- Each frame card:
  - <img src={frame.url}> (served from backend static)
  - Filename below (truncated)
  - If potentially_blurry: orange badge "⚠ blurry" overlay
  - Checkbox for selection (appears on hover or always visible)
- Bulk delete button (appears when selection > 0): calls DELETE /api/files/{id}/frames
- Frame count badge at top: "N frames extracted"
- VRAM estimate: rough formula: N_frames * 5MB → "~Xmb VRAM for RC"
  (display as info badge)
- Loading state: skeleton grid while fetching

### 4. components/panels/PlyViewer.tsx
PLY preview / SuperSplat launcher:
- Props: projectId: string, plyUrl?: string
- If plyUrl provided:
  - Primary: <iframe> embedding supersplat_url from settings + ?load={plyUrl}
    height: 400px, border: 1px solid slate-700
  - Fallback: "Open in SuperSplat" button (opens URL in new tab via window.open)
- If no plyUrl:
  - Placeholder state: "PLY file not ready yet" with a spinner
  - Check exportFiles from store, auto-update when file_ready WS event received
- Download button: <a href={plyUrl} download> if plyUrl available
- Copy path button: copies absolute path to clipboard

## CONSTRAINTS
- No external chart library in this session (recharts used in Session 8 for LFS)
- FrameGallery: use CSS grid (grid-cols-5), not a third-party gallery lib
- PlyViewer iframe: sandbox="allow-scripts allow-same-origin" for security
- All components export as named exports (not default)