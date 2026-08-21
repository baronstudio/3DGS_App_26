import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type {
  Project,
  WsMessage,
  LogEntry,
  StepStatus,
  LfsMetric,
  ExportFile,
  StepName,
  LogLevel,
  ProjectOperation,
} from '../types';

const MAX_LOGS = 500;

interface PipelineState {
  // Projects
  projects: Project[];
  currentProjectId: string | null;

  // Pipeline state
  stepStatuses: Record<number, StepStatus>;
  currentStep: number;
  pipelineRunning: boolean;

  // WebSocket connection status
  wsConnected: boolean;

  // Logs
  logs: LogEntry[];

  // Per-step progress
  stepProgress: Record<string, number>;

  // LFS metrics
  lfsMetrics: LfsMetric[];

  // Export files
  exportFiles: ExportFile[];

  // Project-level file operation in flight (copy / reset / archive / restore)
  projectOp: ProjectOperation | null;

  // Actions — projects
  setProjects: (projects: Project[]) => void;
  addProject: (project: Project) => void;
  upsertProject: (project: Project) => void;
  removeProject: (id: string) => void;
  setCurrentProject: (id: string | null) => void;

  // Actions — project operations
  startProjectOp: (op: { projectId: string; title: string; projectName: string }) => void;
  failProjectOp: (message: string) => void;
  endProjectOp: () => void;

  // Actions — websocket
  setWsConnected: (connected: boolean) => void;

  // Actions — logs
  addLog: (entry: LogEntry) => void;
  clearLogs: () => void;

  // Actions — pipeline
  setCurrentStep: (step: number) => void;
  setStepStatus: (step: number, status: StepStatus) => void;
  setStepProgress: (step: StepName, progress: number) => void;
  setPipelineRunning: (running: boolean) => void;
  confirmStep: (step: number) => void;

  // Actions — LFS metrics
  addLfsMetric: (metric: LfsMetric) => void;
  clearLfsMetrics: () => void;

  // Actions — export files
  setExportFiles: (files: ExportFile[]) => void;
  addExportFile: (file: ExportFile) => void;

  // Hydrate wizard state from a persisted project (on project selection / page reload)
  hydrateFromProject: (project: Project) => void;

  // WebSocket message dispatcher
  handleWsMessage: (msg: WsMessage) => void;
}

const stepNameToIndex: Record<StepName, number> = {
  extract: 2,
  // Curation is step 2's second phase, so it reports against the same step.
  curate: 2,
  rc: 3,
  lfs: 4,
  export: 5,
  blender: 6,
};

let logCounter = 0;

export const usePipelineStore = create<PipelineState>()(
  immer((set) => ({
    // Initial state
    projects: [],
    currentProjectId: null,

    stepStatuses: { 1: 'pending', 2: 'pending', 3: 'pending', 4: 'pending', 5: 'pending', 6: 'pending' },
    currentStep: 1,
    pipelineRunning: false,

    wsConnected: false,
    logs: [],
    stepProgress: {},
    lfsMetrics: [],
    exportFiles: [],
    projectOp: null,

    // Project actions
    setProjects: (projects) =>
      set((state) => { state.projects = projects; }),

    addProject: (project) =>
      set((state) => { state.projects.push(project); }),

    // Copy / reset / archive all hand back the whole project row, so the list
    // takes it as-is rather than re-fetching everything for one changed tile.
    upsertProject: (project) =>
      set((state) => {
        const index = state.projects.findIndex((p) => p.id === project.id);
        if (index === -1) state.projects.push(project);
        else state.projects[index] = project;
      }),

    removeProject: (id) =>
      set((state) => {
        state.projects = state.projects.filter((p) => p.id !== id);
        if (state.currentProjectId === id) state.currentProjectId = null;
      }),

    setCurrentProject: (id) =>
      set((state) => { state.currentProjectId = id; }),

    // Project operation actions. The modal is opened by the request that starts
    // the work and closed by the one that finishes it; what happens in between
    // arrives on the WS bus under the step name 'project'.
    startProjectOp: ({ projectId, title, projectName }) =>
      set((state) => {
        state.projectOp = {
          projectId, title, projectName,
          progress: 0,
          message: 'Starting…',
          error: null,
        };
      }),

    failProjectOp: (message) =>
      set((state) => {
        if (state.projectOp) state.projectOp.error = message;
      }),

    endProjectOp: () =>
      set((state) => { state.projectOp = null; }),

    // WebSocket connection status
    setWsConnected: (connected) =>
      set((state) => { state.wsConnected = connected; }),

    // Log actions
    addLog: (entry) =>
      set((state) => {
        state.logs.push(entry);
        if (state.logs.length > MAX_LOGS) {
          state.logs = state.logs.slice(state.logs.length - MAX_LOGS);
        }
      }),

    clearLogs: () =>
      set((state) => { state.logs = []; }),

    // Pipeline actions
    setCurrentStep: (step) =>
      set((state) => { state.currentStep = step; }),

    setStepStatus: (step, status) =>
      set((state) => { state.stepStatuses[step] = status; }),

    setStepProgress: (step, progress) =>
      set((state) => { state.stepProgress[step] = progress; }),

    setPipelineRunning: (running) =>
      set((state) => { state.pipelineRunning = running; }),

    confirmStep: (step) =>
      set((state) => { state.stepStatuses[step] = 'done'; }),

    // LFS metrics actions
    addLfsMetric: (metric) =>
      set((state) => { state.lfsMetrics.push(metric); }),

    clearLfsMetrics: () =>
      set((state) => { state.lfsMetrics = []; }),

    // Export file actions
    setExportFiles: (files) =>
      set((state) => { state.exportFiles = files; }),

    addExportFile: (file) =>
      set((state) => { state.exportFiles.push(file); }),

    // Restore wizard state from a saved project
    hydrateFromProject: (project) =>
      set((state) => {
        const prevStatuses = { ...state.stepStatuses };
        const prevCurrentStep = state.currentStep;

        // Reset all steps to pending, then apply persisted statuses
        state.stepStatuses = { 1: 'pending', 2: 'pending', 3: 'pending', 4: 'pending', 5: 'pending', 6: 'pending' };
        const saved = project.step_status as Record<string, string>;
        if (saved && typeof saved === 'object') {
          Object.entries(saved).forEach(([k, v]) => {
            const idx = parseInt(k, 10);
            if (idx >= 1 && idx <= 6 && ['pending', 'running', 'done', 'error', 'aborted'].includes(v)) {
              state.stepStatuses[idx] = v as StepStatus;
            }
          });
        }
        state.currentStep = Math.max(project.current_step, 1);

        // ── Debug log ──────────────────────────────────────────────────────
        console.debug(
          '[WIZARD-DEBUG] hydrateFromProject',
          `project='${project.name}'`,
          `DB_current_step=${project.current_step} → UI_currentStep=${state.currentStep}`,
          `prev_currentStep=${prevCurrentStep}`,
          `DB_step_status=`, saved,
          `prev_stepStatuses=`, prevStatuses,
          `new_stepStatuses=`, { ...state.stepStatuses },
        );
        state.logs.push({
          id: `hydrate-${++logCounter}`,
          timestamp: new Date().toISOString(),
          step: 'pipeline',
          level: 'DEBUG',
          message:
            `[WIZARD-DEBUG] hydrateFromProject: project='${project.name}'`
            + ` DB_current_step=${project.current_step}→UI=${state.currentStep}`
            + ` stepStatuses=${JSON.stringify(state.stepStatuses)}`
            + ` ⚠️ Watch Step5 useEffect: will auto-start if step4=done & step5=pending & currentStep=5`,
        });
      }),

    // WebSocket message dispatcher
    handleWsMessage: (msg) =>
      set((state) => {
        switch (msg.type) {
          case 'log': {
            if (msg.step === 'project' && state.projectOp && msg.message) {
              state.projectOp.message = msg.message;
            }
            const entry: LogEntry = {
              id: `log-${++logCounter}`,
              timestamp: msg.timestamp,
              step: msg.step,
              level: (msg.level as LogLevel) ?? 'INFO',
              message: msg.message ?? '',
            };
            state.logs.push(entry);
            if (state.logs.length > MAX_LOGS) {
              state.logs = state.logs.slice(state.logs.length - MAX_LOGS);
            }
            break;
          }
          case 'progress': {
            if (msg.step === 'project') {
              // Not a wizard step: the file operations report here, and only
              // the modal cares.
              if (state.projectOp) {
                if (msg.progress !== undefined) state.projectOp.progress = msg.progress;
                if (msg.message) state.projectOp.message = msg.message;
              }
              break;
            }
            if (msg.progress !== undefined) {
              state.stepProgress[msg.step] = msg.progress;
              // progress=1.0 means the step runner completed — update status
              // (fallback for messages that carry progress but no explicit status field)
              if (msg.progress >= 1.0) {
                const stepIdx = stepNameToIndex[msg.step as StepName];
                if (stepIdx !== undefined && state.stepStatuses[stepIdx] === 'running') {
                  const lvl = msg.level ?? 'SUCCESS';
                  if (lvl === 'SUCCESS' || lvl === 'INFO') {
                    state.stepStatuses[stepIdx] = 'done';
                    state.pipelineRunning = false;
                    console.debug(
                      `[WIZARD-DEBUG] progress=1.0 on step ${msg.step}(${stepIdx})`
                      + ' → stepStatuses set to done, pipelineRunning=false',
                    );
                  }
                }
              }
            }
            break;
          }
          case 'metric': {
            if (msg.data) {
              const d = msg.data;
              if (
                d.iteration !== undefined &&
                d.loss !== undefined &&
                d.psnr !== undefined &&
                d.num_gaussians !== undefined
              ) {
                state.lfsMetrics.push({
                  iteration: d.iteration,
                  loss: d.loss,
                  psnr: d.psnr,
                  num_gaussians: d.num_gaussians,
                });
              }
            }
            break;
          }
          case 'status': {
            const stepIdx = stepNameToIndex[msg.step as StepName];
            if (stepIdx !== undefined && msg.level) {
              const statusMap: Record<string, StepStatus> = {
                INFO: 'running',
                SUCCESS: 'done',
                ERROR: 'error',
                WARNING: 'running',
              };
              // msg.status is the explicit state; the level map is only a
              // fallback for older messages that carry no status field. An abort
              // arrives as level=WARNING, which the map reads as 'running' — so
              // without this the aborted step would spin forever.
              const explicit: StepStatus[] = ['running', 'done', 'error', 'aborted'];
              const newStatus = explicit.includes(msg.status as StepStatus)
                ? (msg.status as StepStatus)
                : statusMap[msg.level];
              if (newStatus) {
                const prevStatus = state.stepStatuses[stepIdx];
                state.stepStatuses[stepIdx] = newStatus;
                console.debug(
                  `[WIZARD-DEBUG] WS status: step=${msg.step}(${stepIdx})`
                  + ` ${prevStatus} → ${newStatus}  pipelineRunning=${state.pipelineRunning}`,
                );
                state.logs.push({
                  id: `status-${++logCounter}`,
                  timestamp: msg.timestamp ?? new Date().toISOString(),
                  step: msg.step,
                  level: 'DEBUG',
                  message:
                    `[WIZARD-DEBUG] stepStatus: step=${msg.step}(${stepIdx})`
                    + ` ${prevStatus}→${newStatus}`
                    + (newStatus === 'done'
                      ? ' ✅ Waiting for user click to advance wizard'
                      : ''),
                });
                if (newStatus === 'running') {
                  state.currentStep = stepIdx;
                  state.pipelineRunning = true;
                }
                if (newStatus === 'done' || newStatus === 'error' || newStatus === 'aborted') {
                  // Single-step pipeline: mark as not running as soon as the step finishes
                  state.pipelineRunning = false;
                }
              }
            }
            break;
          }
          case 'file_ready': {
            if (msg.file) {
              state.exportFiles.push({
                filename: msg.file,
                url: `/api/files/${msg.file}`,
                size_bytes: 0,
              });
            }
            break;
          }
        }
      }),
  }))
);
