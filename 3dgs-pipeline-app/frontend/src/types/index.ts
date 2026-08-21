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
  /** Absolute path of projects/<slug>/ on this machine — shown on the tile. */
  path: string;
  /** Archived: the files are zipped away and the project is read-only. */
  archived: boolean;
  archived_at: string | null;
  archive_path: string | null;
}

/**
 * A project-level file operation in flight (copy / reset / archive / restore).
 * It lives in the store, not in the list component, because the list unmounts
 * as soon as the user changes step — and the progress view must not go with it.
 */
export interface ProjectOperation {
  projectId: string;
  /** Imperative title of the modal: "Copying project". */
  title: string;
  projectName: string;
  /** 0 → 1, from the WS bus. */
  progress: number;
  message: string;
  /** Set when the operation failed; the modal then waits to be dismissed. */
  error: string | null;
}

/** Wizard steps a reset can wipe. Step 1 (import) owns the source video and is
 *  never reset — that is the whole point of the option. */
export const RESETTABLE_STEPS = [2, 3, 4, 5, 6] as const;

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

// LichtFeld Studio v0.5.3 strategies. 'default' sends no --strategy flag and
// lets the build pick, which is MRNF.
export type LFSStrategy = 'default' | 'mcmc' | 'mrnf' | 'igs+';

export interface LFSSettingsType {
  iterations: number;
  strategy: LFSStrategy;
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

/** RealityScan's "Undistortion settings" block (CLAUDE.md §7.2). */
export interface UndistortDefaults {
  enabled: boolean;
  fit: 'outer_boundary' | 'inner_region' | 'in_between';
  resolution: 'preserve' | 'custom' | 'fit';
  custom_width: number;
  custom_height: number;
  downscale: number;
  undistort_principal_point: boolean;
  image_cutout: number;
  max_pixels: number;
  export_images: boolean;
  image_format: 'png' | 'jpg' | 'tiff';
  pixel_format: string;
  naming_convention: 'sequential' | 'original';
  background_color: string;
}

/** The COLMAP registration export of step 3. */
export interface ColmapExportDefaults {
  enabled: boolean;
  directory_structure: 'standard' | 'flat';
  file_type: 'binary' | 'ascii';
  exclude_unreliable_tie_points: boolean;
  export_masks: boolean;
  mask_extension: 'ext' | 'mask_ext';
  scene_rotate_x_deg: number;
  undistort: UndistortDefaults;
}

export interface RCDefaults {
  precision: 'Preview' | 'Normal' | 'High';
  max_features: number;
  keep_largest: boolean;
  merge_components: boolean;
  normalise_for_lfs: boolean;
  colmap: ColmapExportDefaults;
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
  strategy: LFSStrategy;
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

export interface ViewerDefaults {
  /** What the 3D preview opens at. 0 opens at full quality. */
  preview_max_points: number;
  point_size: number;
  show_cameras: boolean;
  show_camera_path: boolean;
  background: string;
}

export interface AppDefaults {
  schema_version: number;
  extract: ExtractDefaults;
  curate: CurateDefaults;
  rc: RCDefaults;
  lfs: LFSDefaults;
  export: ExportDefaults;
  blender: BlenderDefaults;
  viewer: ViewerDefaults;
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

// -- 3D viewer (wizard steps 3, 4 and 5) -------------------------------------

export type PreviewSource = 'rc' | 'lfs' | 'export';

/** What the source file turned out to be, not which step wrote it: the RC stub
 *  writes a gaussian PLY where the real RC writes a plain sparse cloud. */
export type PreviewKind = 'cloud' | 'splat';

export interface PreviewState {
  source: PreviewSource;
  available: boolean;
  ready: boolean;
  /** Vertex cap the preview was built at; null means the whole file. */
  max_count: number | null;
  source_file?: string;
  source_bytes?: number;
  source_url?: string;
  kind?: PreviewKind;
  /** Vertices in the source file. */
  total?: number;
  /** URL of the built preview, under /static. */
  url?: string;
  /** Vertices actually in the preview. */
  count?: number;
  bytes?: number;
  decimated?: boolean;
  building?: boolean;
  progress?: number;
  error?: string;
}

export interface CameraPose {
  /** Name in the RC export — renamed to 00000.png when RC undistorted it. */
  name: string;
  position: number[];
  /** Row-major 3x3 rotation of the camera-to-world matrix. */
  basis: number[];
  /** The input frame this camera came from, when the two could be matched. */
  source_name: string | null;
  sequence_id: number | null;
  /** An aligned camera whose neighbour in the input order never came back. */
  gap_edge: boolean;
}

export interface CamerasReport {
  available: boolean;
  count: number;
  cameras: CameraPose[];
  matched_by?: 'name' | 'position' | 'count' | null;
  gaps_known?: boolean;
  missing_count?: number;
  sequence_ids?: number[];
  fov_x?: number | null;
  aspect?: number | null;
}
