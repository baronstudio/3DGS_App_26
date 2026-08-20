export interface Project {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
  current_step: number;
  step_status: Record<string, string>;
  input_video_path: string | null;
  frame_count: number;
  settings_json: string;
  error_message: string | null;
  thumbnail_url: string | null;
}

// 'curate' is the second phase of wizard step 2, not a seventh step: it gets
// its own name so the UI can show its progress separately (CLAUDE.md §6).
export type StepName = 'extract' | 'curate' | 'rc' | 'lfs' | 'export' | 'blender';
export type StepStatus = 'pending' | 'running' | 'done' | 'error' | 'aborted';
export type LogLevel = 'INFO' | 'WARNING' | 'ERROR' | 'SUCCESS' | 'DEBUG';

export interface WsMessage {
  type: 'log' | 'progress' | 'metric' | 'status' | 'file_ready';
  step: string;
  timestamp: string;
  level?: string;
  message?: string;
  progress?: number;
  status?: string;
  data?: {
    iteration?: number;
    total_iterations?: number;
    loss?: number;
    psnr?: number;
    num_gaussians?: number;
    iter_per_sec?: number;
  };
  file?: string;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  step: string;
  level: LogLevel;
  message: string;
}

export interface LfsMetric {
  iteration: number;
  loss: number;
  psnr: number;
  num_gaussians: number;
}

export interface ExportFile {
  filename: string;
  url: string;
  size_bytes: number;
}

export interface RCSettingsType {
  precision: "Preview" | "Normal" | "High";
  max_features: number;
  keep_largest: boolean;
  merge_components: boolean;
  rsbox_path?: string;
  stub_enabled: boolean;
  stub_duration: number;
}

export interface LFSSettingsType {
  iterations: number;
  strategy: "default" | "mcmc";
  lr: number;
  save_interval: number;
  render_mode: string;
  eval: boolean;
  save_eval_images: boolean;
  background_color: string;
  stub_enabled: boolean;
  stub_duration: number;
}

// ── App defaults (defaults.json — layer 2 of the settings model) ─────────────

export type FpsMode = 'auto' | 'ratio' | 'absolute';

export interface CapturePreset {
  id: string;
  label: string;
  target_frame_count: number;
  min_fps: number;
  max_fps: number;
  overlap_min_step_pct: number;
  overlap_band_max_pct: number;
  notes: string;
}

export interface ExtractDefaults {
  capture_preset: string;
  fps_mode: FpsMode;
  fps_ratio: number;
  fps_absolute: number;
  target_frame_count: number;
  mpdecimate: boolean;
  quality: number;
  max_frames: number;
}

export interface CurateDefaults {
  enabled: boolean;
  auto_after_extract: boolean;
  scene_detector: 'adaptive' | 'content' | 'off';
  min_scene_len: number;
  sharpness_window: number;
  sharpness_sensitivity: number;
  /** When on, the overlap band comes from the active capture preset (§6.2). */
  overlap_from_preset: boolean;
  overlap_min_step_pct: number;
  overlap_band_max_pct: number;
}

export interface RCDefaults {
  precision: 'Preview' | 'Normal' | 'High';
  max_features: number;
  keep_largest: boolean;
  merge_components: boolean;
  extra_align_commands: string[];
}

/** Coverage of the last alignment — rc_output/alignment_check.json (§7). */
export interface AlignmentSequenceStat {
  sequence_id: number;
  input: number;
  aligned: number;
  missing: number;
}

export interface AlignmentReport {
  checked: boolean;
  reason: string | null;
  input_count: number;
  aligned_count: number;
  missing_count: number;
  aligned_ratio: number | null;
  single_component: boolean | null;
  missing_frames: string[];
  sequences: AlignmentSequenceStat[];
  source: string | null;
}

export interface LFSDefaults {
  iterations: number;
  strategy: 'default' | 'mcmc';
  lr: number;
  save_interval: number;
  render_mode: string;
  eval: boolean;
  save_eval_images: boolean;
  background_color: string;
}

export interface ExportDefaults {
  format: 'ply' | 'splat';
  pattern: string;
}

export interface BlenderDefaults {
  scene_scale: number;
  import_mode: string;
}

export interface AppDefaults {
  schema_version: number;
  extract: ExtractDefaults;
  curate: CurateDefaults;
  rc: RCDefaults;
  lfs: LFSDefaults;
  export: ExportDefaults;
  blender: BlenderDefaults;
}

export type DefaultsSection = keyof Omit<AppDefaults, 'schema_version'>;

// ── Curation (wizard step 2, phase 2 — CLAUDE.md §6.3) ───────────────────────

export type Verdict = 'kept' | 'rejected';
export type RejectReason = 'blur' | 'redundant' | 'manual';
export type Override = 'keep' | 'drop';

export interface FrameInfo {
  filename: string;
  path: string;
  size_bytes: number;
  url: string;
  index: number;
  sequence_id: number | null;
  sharpness: number | null;
  sharpness_median: number | null;
  displacement_pct: number | null;
  /** null before the first analysis — an unanalysed set has no verdict. */
  verdict: Verdict | null;
  reason: RejectReason | null;
  warning: 'gap' | null;
  override: Override | null;
}

export interface SelectionSummary {
  total: number;
  removed: number;
  removed_pct: number;
  kept: number;
  rejected_blur: number;
  rejected_redundant: number;
  rejected_manual: number;
  kept_manual: number;
  warning_gap: number;
}

export interface FramesResponse {
  frames: FrameInfo[];
  total: number;
  kept_count: number;
  rejected_count: number;
  warning_count: number;
  analysed: boolean;
  summary: SelectionSummary | null;
}

export interface FrameScore {
  index: number;
  filename: string;
  sequence_id: number;
  sharpness: number;
  sharpness_median: number;
  displacement_pct: number | null;
  auto_verdict: Verdict;
  auto_reason: RejectReason | null;
  warning: 'gap' | null;
}

export interface SequenceSpan {
  id: number;
  start_index: number;
  end_index: number;
  frame_count: number;
}

export interface CurationScores {
  generated_at: string;
  params: CurateDefaults & {
    scene_method: string;
    band_source: string;
    working_fps: number | null;
  };
  sequences: SequenceSpan[];
  stats: {
    sharpness_all: { mean: number; median: number; min: number; max: number };
    sharpness_kept: { mean: number; median: number; min: number; max: number };
    overlap: { pairs: number; in_band: number; in_band_ratio: number; median_pct: number };
  };
  frames: FrameScore[];
}

export interface CurationSelection {
  generated_at: string;
  kept: string[];
  rejected: { frame: string; reason: RejectReason; index: number }[];
  warnings: { frame: string; reason: 'gap'; index: number }[];
  sequences: { id: number; frame_count: number; kept: number }[];
  summary: SelectionSummary;
}

export interface AnalysisResponse {
  scores: CurationScores | null;
  selection: CurationSelection | null;
  overrides: Record<string, Override>;
  extract: {
    working_fps: number | null;
    fps_explanation: string;
    input_video: string | null;
    mpdecimate: boolean;
    capture_preset: string;
    frame_count: number;
  } | null;
  analysed: boolean;
}
