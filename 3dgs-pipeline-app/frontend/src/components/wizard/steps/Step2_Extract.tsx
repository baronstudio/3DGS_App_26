import React, { useState } from 'react';
import { Settings, ChevronRight, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePipelineStore } from '@/store/pipelineStore';
import { usePipeline } from '@/hooks/usePipeline';
import { useSettings } from '@/hooks/useSettings';
import { ProgressBar } from '@/components/panels/ProgressBar';
import { FrameGallery } from '@/components/panels/FrameGallery';
import FFmpegSettings from '@/components/settings/FFmpegSettings';
import type { FFmpegSettingsType } from '@/types';

const DEFAULT_FFMPEG: FFmpegSettingsType = {
  fps: 2,
  mpdecimate: true,
  quality: 2,
  max_frames: 0,
};

const Step2_Extract: React.FC = () => {
  const { currentProjectId, stepStatuses, setCurrentStep } = usePipelineStore();
  const { startPipeline } = usePipeline();
  const { settings } = useSettings();
  const [showSettings, setShowSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ffmpegSettings, setFfmpegSettings] = useState<FFmpegSettingsType>(DEFAULT_FFMPEG);

  const status = stepStatuses[2];  // step 2 = extract
  const isRunning = status === 'running';
  const isDone = status === 'done';

  const handleExtract = async () => {
    if (!currentProjectId) return;
    setError(null);
    try {
      await startPipeline(currentProjectId, 2, ffmpegSettings);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start extraction';
      setError(msg);
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-2xl mx-auto">
      <h2 className="text-xl font-semibold text-slate-100">Step 2 — Frame Extraction</h2>

      {/* Settings summary */}
      <div className="flex items-center justify-between rounded-lg bg-slate-800 border border-slate-700 px-4 py-3">
        <div className="flex gap-4 text-sm text-slate-300">
          <span>FPS: <span className="text-slate-100 font-medium">{ffmpegSettings.fps}</span></span>
          <span>Quality: <span className="text-slate-100 font-medium">{ffmpegSettings.quality}</span></span>
          <span>Dedup: <span className="text-slate-100 font-medium">{ffmpegSettings.mpdecimate ? 'on' : 'off'}</span></span>
          {settings?.tools?.ffmpeg_path && (
            <span className="text-slate-500 truncate max-w-xs">ffmpeg: {settings.tools.ffmpeg_path}</span>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowSettings((v) => !v)}
          className="text-slate-400 hover:text-slate-100 gap-1"
        >
          <Settings className="w-4 h-4" />
          Advanced
        </Button>
      </div>

      {showSettings && (
        <div className="rounded-lg bg-slate-800 border border-slate-700 p-4">
          <FFmpegSettings settings={ffmpegSettings} onChange={setFfmpegSettings} />
        </div>
      )}

      {error && (
        <p className="text-sm text-red-400 bg-red-950/30 border border-red-800 rounded px-3 py-2">
          {error}
        </p>
      )}

      <Button
        onClick={handleExtract}
        disabled={isRunning || !currentProjectId}
        className="bg-cyan-600 hover:bg-cyan-500 text-white"
      >
        {isRunning ? 'Extracting…' : 'Extract Frames'}
      </Button>

      {(isRunning || isDone) && (
        <ProgressBar step="extract" label="Frame Extraction" />
      )}

      {currentProjectId && (isRunning || isDone) && (
        <FrameGallery projectId={currentProjectId} />
      )}

      {isDone && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-green-400 font-medium">Extraction complete</span>
          <Button
            onClick={() => setCurrentStep(3)}
            className="bg-green-700 hover:bg-green-600 text-white gap-1"
          >
            <CheckCircle className="w-4 h-4" />
            Validate &amp; Continue to RC Alignment
          </Button>
        </div>
      )}
    </div>
  );
};

export default Step2_Extract;
