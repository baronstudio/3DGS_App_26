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

  // Logs
  logs: LogEntry[];

  // Per-step progress
  stepProgress: Record<string, number>;

  // LFS metrics
  lfsMetrics: LfsMetric[];

  // Export files
  exportFiles: ExportFile[];

  // Actions — projects
  setProjects: (projects: Project[]) => void;
  addProject: (project: Project) => void;
  removeProject: (id: string) => void;
  setCurrentProject: (id: string | null) => void;

  // Actions — logs
  addLog: (entry: LogEntry) => void;
  clearLogs: () => void;

  // Actions — pipeline
  setCurrentStep: (step: number) => void;
  setStepStatus: (step: number, status: StepStatus) => void;
  setStepProgress: (step: StepName, progress: number) => void;
  setPipelineRunning: (running: boolean) => void;

  // Actions — LFS metrics
  addLfsMetric: (metric: LfsMetric) => void;
  clearLfsMetrics: () => void;

  // Actions — export files
  setExportFiles: (files: ExportFile[]) => void;
  addExportFile: (file: ExportFile) => void;

  // WebSocket message dispatcher
  handleWsMessage: (msg: WsMessage) => void;
}

const stepNameToIndex: Record<StepName, number> = {
  extract: 2,
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

    logs: [],
    stepProgress: {},
    lfsMetrics: [],
    exportFiles: [],

    // Project actions
    setProjects: (projects) =>
      set((state) => { state.projects = projects; }),

    addProject: (project) =>
      set((state) => { state.projects.push(project); }),

    removeProject: (id) =>
      set((state) => {
        state.projects = state.projects.filter((p) => p.id !== id);
        if (state.currentProjectId === id) state.currentProjectId = null;
      }),

    setCurrentProject: (id) =>
      set((state) => { state.currentProjectId = id; }),

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

    // WebSocket message dispatcher
    handleWsMessage: (msg) =>
      set((state) => {
        switch (msg.type) {
          case 'log': {
            const entry: LogEntry = {
              id: `log-${++logCounter}`,
              timestamp: msg.timestamp,
              step: msg.step,
              level: msg.level ?? 'INFO',
              message: msg.message ?? '',
            };
            state.logs.push(entry);
            if (state.logs.length > MAX_LOGS) {
              state.logs = state.logs.slice(state.logs.length - MAX_LOGS);
            }
            break;
          }
          case 'progress': {
            if (msg.progress !== undefined) {
              state.stepProgress[msg.step] = msg.progress;
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
            const stepIdx = stepNameToIndex[msg.step];
            if (stepIdx !== undefined && msg.level) {
              const statusMap: Record<string, StepStatus> = {
                INFO: 'running',
                SUCCESS: 'done',
                ERROR: 'error',
                WARNING: 'running',
              };
              const newStatus = statusMap[msg.level];
              if (newStatus) {
                state.stepStatuses[stepIdx] = newStatus;
                if (newStatus === 'running') {
                  state.currentStep = stepIdx;
                  state.pipelineRunning = true;
                }
                if (newStatus === 'done' || newStatus === 'error') {
                  const allDone = Object.values(state.stepStatuses).every(
                    (s) => s === 'done' || s === 'error'
                  );
                  if (allDone) state.pipelineRunning = false;
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
