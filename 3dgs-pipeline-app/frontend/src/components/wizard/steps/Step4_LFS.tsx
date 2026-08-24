import React, { useState } from 'react';
import { Settings, Square, CheckCircle } from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { Button } from '@/components/ui/button';
import { usePipelineStore } from '@/store/pipelineStore';
import { usePipeline } from '@/hooks/usePipeline';
import { useDefaults } from '@/hooks/useDefaults';
import { useProjectSettings } from '@/hooks/useProjectSettings';
import { ProgressBar } from '@/components/panels/ProgressBar';
import SceneViewer from '@/components/viewer/SceneViewer';
import LFSSettings from '@/components/settings/LFSSettings';
import SaveState from '@/components/settings/SaveState';
import type { LFSDefaults } from '@/types';

const Step4_LFS: React.FC = () => {
  const { currentProjectId, stepStatuses, lfsMetrics, pipelineRunning, setCurrentStep,
    clearLfsMetrics } = usePipelineStore();
  const { startPipeline, controlPipeline } = usePipeline();
  const { defaults } = useDefaults();
  const [showSettings, setShowSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The panel was seeded from a hardcoded copy of the defaults and thrown away
  // on unmount. It is now defaults.json under this project's overrides, saved
  // on every change (CLAUDE.md §4).
  const {
    value: lfsSettings, setValue: setLfsSettings, flush: flushLfs,
    saving, savedAt, error: saveError,
  } = useProjectSettings<LFSDefaults>(currentProjectId, 'lfs', defaults?.lfs ?? null);

  const status = stepStatuses[4];  // step 4 = lfs
  const isRunning = status === 'running';
  const isDone = status === 'done';

  const lastMetric = lfsMetrics[lfsMetrics.length - 1];
  const gaussianCount = lastMetric?.num_gaussians ?? null;

  const handleStart = async () => {
    if (!currentProjectId || !lfsSettings) return;
    setError(null);
    // The run about to start wipes lfs_output/ (step_lfs resets step 4), so the
    // curve on screen describes a training that no longer exists on disk. Drop
    // it on the click rather than letting the new points be appended to it.
    clearLfsMetrics();
    try {
      // The Advanced panel is the per-project override layer (CLAUDE.md §4);
      // sending {} here made every knob in it decorative.
      const { iterations, strategy, max_gaussians, eval: evalMode,
        save_eval_images, background_color } = lfsSettings;
      await flushLfs();  // land any debounced edit before the run reads the row
      await startPipeline(currentProjectId, 4, {
        lfs: {
          iterations, strategy, max_gaussians, eval: evalMode,
          save_eval_images, background_color,
        },
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start training';
      setError(msg);
    }
  };

  // Abort only: LichtFeld Studio has no pause verb, and a Pause button that
  // cannot stop the training is worse than no button at all.
  const handleAbort = async () => {
    if (!currentProjectId) return;
    try {
      await controlPipeline(currentProjectId, 'abort');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to abort';
      setError(msg);
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-2xl mx-auto">
      <h2 className="text-xl font-semibold text-slate-100">Step 4 — LichtFeld Studio Training</h2>

      <div className="flex items-center justify-between rounded-lg bg-slate-800 border border-slate-700 px-4 py-3">
        <span className="text-sm text-slate-400">3D Gaussian Splatting training</span>
        <div className="flex items-center gap-1">
          <SaveState saving={saving} savedAt={savedAt} error={saveError} />
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
      </div>

      {showSettings && lfsSettings && (
        <div className="rounded-lg bg-slate-800 border border-slate-700 p-4">
          <LFSSettings settings={lfsSettings} onChange={setLfsSettings} />
        </div>
      )}

      {error && (
        <p className="text-sm text-red-400 bg-red-950/30 border border-red-800 rounded px-3 py-2">
          {error}
        </p>
      )}

      <Button
        onClick={handleStart}
        disabled={isRunning || !currentProjectId || !lfsSettings}
        className="bg-cyan-600 hover:bg-cyan-500 text-white"
      >
        {isRunning ? 'Training…' : 'Start Training'}
      </Button>

      {(isRunning || isDone) && (
        <ProgressBar step="lfs" label="LFS Training" />
      )}

      {/* Gaussian count badge */}
      {gaussianCount !== null && (
        <div className="inline-flex items-center gap-2 self-start px-3 py-1 rounded-full bg-slate-700 border border-slate-600 text-sm">
          <span className="text-slate-400">Gaussians:</span>
          <span className="text-cyan-300 font-semibold">{gaussianCount.toLocaleString()}</span>
        </div>
      )}

      {/* Training chart */}
      {lfsMetrics.length > 0 && (
        <div className="rounded-lg bg-slate-800 border border-slate-700 p-3">
          <p className="text-xs text-slate-400 mb-2">Training metrics</p>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={lfsMetrics} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
              <XAxis
                dataKey="iteration"
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                tickLine={false}
              />
              <YAxis
                yAxisId="loss"
                domain={[0, 0.2]}
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                tickLine={false}
                width={40}
              />
              <YAxis
                yAxisId="psnr"
                orientation="right"
                domain={[15, 32]}
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                tickLine={false}
                width={40}
              />
              <Tooltip
                contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: 6 }}
                labelStyle={{ color: '#94a3b8', fontSize: 11 }}
                itemStyle={{ fontSize: 11 }}
              />
              <Line
                yAxisId="loss"
                type="monotone"
                dataKey="loss"
                stroke="#ef4444"
                dot={false}
                strokeWidth={1.5}
                name="Loss"
              />
              {/* PSNR only exists on the `[Evaluation at step N]` lines an
                  --eval run prints, so it is a handful of points scattered
                  through a series that otherwise has none — without
                  connectNulls recharts draws them as invisible isolated dots. */}
              <Line
                yAxisId="psnr"
                type="monotone"
                dataKey="psnr"
                stroke="#00D4FF"
                dot={false}
                connectNulls
                strokeWidth={1.5}
                name="PSNR (dB)"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Control buttons — abort only, see handleAbort */}
      {isRunning && pipelineRunning && currentProjectId && (
        <div className="flex items-center gap-3">
          <Button
            variant="destructive"
            size="sm"
            onClick={handleAbort}
            className="gap-1"
          >
            <Square className="w-4 h-4" />
            Abort
          </Button>
          <span className="text-xs text-slate-500">
            Kills LichtFeld Studio and frees the GPU. Training cannot be paused.
          </span>
        </div>
      )}

      {/* The trained splat. Loss and PSNR say the optimiser converged; only
          this says it converged onto the scene you shot. */}
      {currentProjectId && !isRunning && (
        <div className="rounded-lg bg-slate-800 border border-slate-700 p-3 space-y-2">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">
            Trained splat
          </p>
          <SceneViewer
            projectId={currentProjectId}
            source="lfs"
            refreshKey={status}
            height={440}
          />
        </div>
      )}

      {isDone && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-green-400 font-medium">Training complete</span>
          <Button
            onClick={() => setCurrentStep(5)}
            className="bg-green-700 hover:bg-green-600 text-white gap-1"
          >
            <CheckCircle className="w-4 h-4" />
            Validate &amp; Continue to Export
          </Button>
        </div>
      )}
    </div>
  );
};

export default Step4_LFS;
