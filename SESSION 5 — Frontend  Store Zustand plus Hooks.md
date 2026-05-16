## CONTEXT
Project: 3DGS Pipeline Web App — React 18 + TypeScript + Vite + Zustand
Working dir: c:\Travail\DEV\3DGS_App_26\3dgs-pipeline-app\frontend\
Backend WS: ws://localhost:8000/ws/logs
Backend REST: http://localhost:8000/api

## WS MESSAGE PROTOCOL (from backend broadcast())
interface WsMessage {
  type: "log" | "progress" | "metric" | "status" | "file_ready";
  step: "extract" | "rc" | "lfs" | "export" | "blender";
  timestamp: string;
  level?: "INFO" | "WARNING" | "ERROR" | "SUCCESS";
  message?: string;
  progress?: number;  // 0.0–1.0
  data?: { iteration?: number; total_iterations?: number; loss?: number; psnr?: number; num_gaussians?: number; iter_per_sec?: number; };
  file?: string;
}

## CURRENT STATE
- store/pipelineStore.ts: empty (interface PipelineState {}, no state)
- hooks/useWebSocket.ts: basic, no protocol parsing, no store integration
- hooks/usePipeline.ts: calls API but no state
- hooks/useProjects.ts: exists but unknown state

## TASK

### 1. store/pipelineStore.ts
Full Zustand store (use zustand v4 syntax: import { create } from 'zustand'):

State shape:
  // Projects
  projects: Project[]
  currentProjectId: string | null
  
  // Pipeline state
  stepStatuses: Record<number, "pending" | "running" | "done" | "error">  // 1-6
  currentStep: number
  pipelineRunning: boolean
  
  // Logs (keep last 500)
  logs: LogEntry[]  // { id, timestamp, step, level, message }
  
  // Per-step progress
  stepProgress: Record<string, number>  // step name → 0.0-1.0
  
  // LFS metrics for charts
  lfsMetrics: { iteration: number; loss: number; psnr: number; num_gaussians: number; }[]
  
  // Export files
  exportFiles: { filename: string; url: string; size_bytes: number }[]
  
  // Actions
  setProjects, addProject, removeProject, setCurrentProject
  addLog, clearLogs
  setStepStatus, setStepProgress
  addLfsMetric, clearLfsMetrics
  setPipelineRunning
  setExportFiles, addExportFile
  handleWsMessage(msg: WsMessage)  ← dispatches to appropriate setters based on msg.type

### 2. hooks/useWebSocket.ts
Rewrite to:
  - Connect to ws://localhost:8000/ws/logs
  - Parse incoming JSON as WsMessage
  - Call pipelineStore.getState().handleWsMessage(msg) for each message
  - Auto-reconnect on disconnect (exponential backoff, max 5 attempts)
  - Export: useWebSocket() hook that auto-connects on mount
  - Expose: { connected: boolean, lastMessage: WsMessage | null }

### 3. hooks/useProjects.ts
  - fetchProjects() → GET /api/projects/ → update store
  - createProject(name: string, settings?: object) → POST /api/projects/create → update store
  - deleteProject(id: string) → DELETE /api/projects/{id} → update store
  - selectProject(id: string) → setCurrentProject in store
  - Auto-fetch on mount

### 4. hooks/usePipeline.ts
  - startPipeline(projectId: string, fromStep: number, settings: object) 
    → POST /api/pipeline/start → set pipelineRunning=true in store
  - controlPipeline(projectId: string, action: "pause"|"resume"|"abort")
    → POST /api/pipeline/control
  - fetchStatus(projectId: string) → GET /api/pipeline/status?project_id={id}
  - Expose: { startPipeline, controlPipeline, fetchStatus }

## TypeScript types to define in src/types/index.ts (create this file):
  Project, WsMessage, LogEntry, StepStatus, LfsMetric, ExportFile

## CONSTRAINTS
- zustand v4: import { create } from 'zustand' (NOT import create from 'zustand')
- Use immer for nested state updates if needed: import { immer } from 'zustand/middleware/immer'
- handleWsMessage must be synchronous (called from WS event handler)
- Keep last 500 log entries (slice if longer)