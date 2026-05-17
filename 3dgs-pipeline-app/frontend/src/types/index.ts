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

export type StepName = 'extract' | 'rc' | 'lfs' | 'export' | 'blender';
export type StepStatus = 'pending' | 'running' | 'done' | 'error';
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

export interface FFmpegSettingsType {
  fps: number;
  mpdecimate: boolean;
  quality: number;
  max_frames: number;
}

export interface RCSettingsType {
  precision: "Preview" | "Normal" | "High";
  max_features: number;
  keep_largest: boolean;
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
