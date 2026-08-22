import React, { useEffect, useState } from 'react';
import { Settings, CheckCircle, RefreshCw, Sliders } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePipelineStore } from '@/store/pipelineStore';
import { usePipeline } from '@/hooks/usePipeline';
import { useSettings } from '@/hooks/useSettings';
import { useDefaults } from '@/hooks/useDefaults';
import { useCuration } from '@/hooks/useCuration';
import { ProgressBar } from '@/components/panels/ProgressBar';
import { FrameGallery } from '@/components/panels/FrameGallery';
import { SharpnessTimeline } from '@/components/panels/SharpnessTimeline';
import FFmpegSettings from '@/components/settings/FFmpegSettings';
import CurateSettings from '@/components/settings/CurateSettings';
import client from '@/api/client';
import type { CurateDefaults, ExtractDefaults, SelectionSummary } from '@/types';

/** One stat of the curation summary. */
const Stat: React.FC<{ label: string; value: string; tone?: string; hint?: string }> = ({
  label, value, tone = 'text-slate-100', hint,
}) => (
  <div className="flex flex-col" title={hint}>
    <span className={`text-lg font-semibold ${tone}`}>{value}</span>
    <span className="text-[11px] text-slate-500 uppercase tracking-wide">{label}</span>
  </div>
);

const CurationSummary: React.FC<{ summary: SelectionSummary; inBandRatio?: number }> = ({
  summary, inBandRatio,
}) => (
  <div className="rounded-lg bg-slate-800 border border-slate-700 px-4 py-3">
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
      <Stat label="kept" value={`${summary.kept}/${summary.total}`} tone="text-green-400" />
      <Stat
        label="removed"
        value={`${summary.removed_pct.toFixed(1)}%`}
        tone="text-red-400"
        hint={`${summary.rejected_blur} blur, ${summary.rejected_redundant} redundant, ${summary.rejected_manual} manual`}
      />
      <Stat label="blur" value={String(summary.rejected_blur)} tone="text-red-300" />
      <Stat label="redundant" value={String(summary.rejected_redundant)} tone="text-purple-300" />
      <Stat
        label="gaps"
        value={String(summary.warning_gap)}
        tone={summary.warning_gap > 0 ? 'text-amber-400' : 'text-slate-400'}
        hint="Frames whose step exceeds the band — the likely alignment breaks."
      />
    </div>
    {inBandRatio !== undefined && (
      <p className="text-xs text-slate-500 mt-2">
        {(inBandRatio * 100).toFixed(0)}% of consecutive kept pairs sit inside the overlap band.
      </p>
    )}
  </div>
);

const Step2_Extract: React.FC = () => {
  const { currentProjectId, stepStatuses, setCurrentStep } = usePipelineStore();
  const { startPipeline } = usePipeline();
  const { settings } = useSettings();
  const { defaults, presets, previewFps } = useDefaults();
  const {
    frames, summary, analysis, analysed, loading,
    reanalyse, setOverride, refresh, error: curationError,
  } = useCuration(currentProjectId);

  const [showSettings, setShowSettings] = useState(false);
  const [showCurate, setShowCurate] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Per-project working copies, seeded from the app defaults (CLAUDE.md §4).
  const [extract, setExtract] = useState<ExtractDefaults | null>(null);
  const [curate, setCurate] = useState<CurateDefaults | null>(null);
  const [probe, setProbe] = useState<{ fps: number | null; duration_s: number | null } | null>(null);
  const [fpsExplanation, setFpsExplanation] = useState<string>('');

  const status = stepStatuses[2];  // step 2 = extract + curate
  const isRunning = status === 'running';
  const isDone = status === 'done';

  // Seed once the defaults arrive; do not clobber edits made since.
  useEffect(() => {
    setExtract((cur) => cur ?? defaults?.extract ?? null);
    setCurate((cur) => cur ?? defaults?.curate ?? null);
  }, [defaults]);

  // The source metadata only exists after a first extraction — absent is fine.
  useEffect(() => {
    if (!currentProjectId) return;
    client
      .get(`/files/${currentProjectId}/probe`)
      .then((r) => setProbe(r.data?.probe ?? null))
      .catch(() => setProbe(null));
  }, [currentProjectId, isDone]);

  // Resolve the policy against this project's real source when we know it.
  useEffect(() => {
    if (!extract) return;
    const t = setTimeout(() => {
      previewFps(extract, probe?.fps ?? null, probe?.duration_s ?? null)
        .then((r) => setFpsExplanation(r.explanation))
        .catch(() => setFpsExplanation(''));
    }, 250);
    return () => clearTimeout(t);
  }, [extract, probe, previewFps]);

  /** Everything the backend needs to resolve both phases of step 2. */
  const jobSettings = () => ({ ...(extract ?? {}), curate: curate ?? {} });

  const handleExtract = async () => {
    if (!currentProjectId || !extract) return;
    setError(null);
    try {
      await startPipeline(currentProjectId, 2, jobSettings());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start extraction');
    }
  };

  const handleReanalyse = async () => {
    setError(null);
    try {
      await reanalyse(jobSettings());
    } catch {
      /* surfaced through curationError */
    }
  };

  const handleDelete = async (filenames: string[]) => {
    if (!currentProjectId || filenames.length === 0) return;
    try {
      await client.delete(`/files/${currentProjectId}/frames`, { data: { filenames } });
      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete frames');
    }
  };

  const fpsSummary = extract
    ? extract.fps_mode === 'auto'
      ? `auto → ${extract.target_frame_count} frames`
      : extract.fps_mode === 'ratio'
        ? `ratio ${extract.fps_ratio}`
        : `${extract.fps_absolute} fps`
    : '—';

  const activePreset = presets.find((p) => p.id === extract?.capture_preset);
  const hasFrames = frames.length > 0;

  return (
    <div className="flex flex-col gap-6 p-6 max-w-4xl mx-auto">
      <h2 className="text-xl font-semibold text-slate-100">
        Step 2 — Frame Extraction &amp; Curation
      </h2>

      {/* Settings summary */}
      <div className="flex items-center justify-between rounded-lg bg-slate-800 border border-slate-700 px-4 py-3 flex-wrap gap-2">
        <div className="flex gap-4 text-sm text-slate-300 flex-wrap">
          <span>FPS: <span className="text-slate-100 font-medium">{fpsSummary}</span></span>
          <span>Quality: <span className="text-slate-100 font-medium">{extract?.quality ?? '—'}</span></span>
          <span>Dedup: <span className="text-slate-100 font-medium">{extract?.mpdecimate ? 'on' : 'off'}</span></span>
          <span>
            Curation:{' '}
            <span className={curate?.enabled ? 'text-cyan-400 font-medium' : 'text-slate-500 font-medium'}>
              {curate?.enabled ? 'on' : 'off'}
            </span>
          </span>
          {settings?.tools?.ffmpeg_path && (
            <span className="text-slate-500 truncate max-w-xs">ffmpeg: {settings.tools.ffmpeg_path}</span>
          )}
        </div>
        <div className="flex gap-1">
          <Button
            variant="ghost" size="sm"
            onClick={() => { setShowSettings((v) => !v); setShowCurate(false); }}
            className="text-slate-400 hover:text-slate-100 gap-1"
          >
            <Settings className="w-4 h-4" />
            Extraction
          </Button>
          <Button
            variant="ghost" size="sm"
            onClick={() => { setShowCurate((v) => !v); setShowSettings(false); }}
            className="text-slate-400 hover:text-slate-100 gap-1"
          >
            <Sliders className="w-4 h-4" />
            Curation
          </Button>
        </div>
      </div>

      {fpsExplanation && !showSettings && (
        <p className="text-xs text-cyan-400 font-mono -mt-3">{fpsExplanation}</p>
      )}

      {showSettings && extract && (
        <div className="rounded-lg bg-slate-800 border border-slate-700 p-4">
          <FFmpegSettings
            settings={extract}
            presets={presets}
            onChange={setExtract}
            fpsExplanation={fpsExplanation}
          />
        </div>
      )}

      {showCurate && curate && (
        <div className="rounded-lg bg-slate-800 border border-slate-700 p-4">
          <CurateSettings settings={curate} preset={activePreset} onChange={setCurate} />
        </div>
      )}

      {(error || curationError) && (
        <p className="text-sm text-red-400 bg-red-950/30 border border-red-800 rounded px-3 py-2">
          {error ?? curationError}
        </p>
      )}

      {/* Actions */}
      <div className="flex gap-2 flex-wrap">
        <Button
          onClick={handleExtract}
          disabled={isRunning || !currentProjectId || !extract}
          className="bg-cyan-600 hover:bg-cyan-500 text-white"
        >
          {isRunning ? 'Working…' : hasFrames ? 'Re-extract Frames' : 'Extract Frames'}
        </Button>
        {/* Re-analysing never re-extracts: thresholds are tuned iteratively (§6.3). */}
        <Button
          onClick={handleReanalyse}
          disabled={isRunning || !hasFrames || !currentProjectId}
          variant="ghost"
          className="border border-slate-700 text-slate-300 hover:text-slate-100 gap-1"
          title="Re-run the curation on the frames already on disk"
        >
          <RefreshCw className="w-4 h-4" />
          Re-analyse
        </Button>
      </div>

      {(isRunning || isDone) && (
        <div className="flex flex-col gap-2">
          <ProgressBar step="extract" label="1. Frame extraction" />
          {curate?.enabled && <ProgressBar step="curate" label="2. Curation" />}
        </div>
      )}

      {/* Curation results */}
      {analysed && summary && (
        <CurationSummary
          summary={summary}
          inBandRatio={analysis?.scores?.stats.overlap.in_band_ratio}
        />
      )}

      {analysis?.scores && analysis.scores.frames.length > 0 && (
        <SharpnessTimeline scores={analysis.scores} />
      )}

      {analysis?.scores && (
        <p className="text-xs text-slate-500 -mt-3">
          {analysis.scores.sequences.length} sequence(s) · {analysis.scores.params.scene_method} ·{' '}
          {analysis.scores.params.band_source}
        </p>
      )}

      {currentProjectId && (hasFrames || isRunning) && (
        <FrameGallery
          frames={frames}
          loading={loading}
          analysed={analysed}
          summary={summary}
          onOverride={setOverride}
          onDelete={handleDelete}
        />
      )}

      {isDone && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-green-400 font-medium">
            {analysed && summary
              ? `${summary.kept} frames selected for alignment`
              : 'Extraction complete'}
          </span>
          <Button
            onClick={() => setCurrentStep(3)}
            className="bg-green-700 hover:bg-green-600 text-white gap-1"
          >
            <CheckCircle className="w-4 h-4" />
            Validate &amp; Continue to RS Alignment
          </Button>
        </div>
      )}
    </div>
  );
};

export default Step2_Extract;
