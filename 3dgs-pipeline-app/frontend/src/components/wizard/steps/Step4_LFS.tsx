import React, { useState } from 'react';
import { Settings, AlertTriangle, Play, Pause, Square } from 'lucide-react';
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
import { useSettings } from '@/hooks/useSettings';
import { ProgressBar } from '@/components/panels/ProgressBar';
import LFSSettings from '@/components/settings/LFSSettings';
import type { LFSSettingsType } from '@/types';

const DEFAULT_LFS: LFSSettingsType = {
  iterations: 30000,
  strategy: 'default',
  lr: 0.001,
  save_interval: 0,
  render_mode: 'RGB',
  eval: false,
  save_eval_images: false,
  background_color: '#000000',
  stub_enabled: false,
  stub_duration: 10,
};

const Step4_LFS: React.FC = () => {
  const { currentProjectId, stepStatuses, lfsMetrics, pipelineRunning, setCurrentStep } =
    usePipelineStore();
  const { startPipeline, controlPipeline } = usePipeline();
  const { settings } = useSettings();
  const [showSettings, setShowSettings] = useState(false);
  const [paused, setPaused] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lfsSettings, setLfsSettings] = useState<LFSSettingsType>(DEFAULT_LFS);

  const status = stepStatuses[3];
  const isRunning = status === 'running';
  const isDone = status === 'done';
  const isStub = settings?.stubs?.lfs_stub ?? false;

  const lastMetric = lfsMetrics[lfsMetrics.length - 1];
  const gaussianCount = lastMetric?.num_gaussians ?? null;

  const handleStart = async () => {
    if (!currentProjectId) return;
    setError(null);
    setPaused(false);
    try {
      await startPipeline(currentProjectId, 4, {});
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start training';
      setError(msg);
    }
  };

  const handleControl = async (action: 'pause' | 'resume' | 'abort') => {
    if (!currentProjectId) return;
    try {
      await controlPipeline(currentProjectId, action);
      if (action === 'pause') setPaused(true);
      if (action === 'resume') setPaused(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to ${action}`;
      setError(msg);
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-2xl mx-auto">
      <h2 className="text-xl font-semibold text-slate-100">Step 4 — LichtFeld Studio Training</h2>

      {isStub && (
        <div className="flex items-center gap-2 rounded-md bg-orange-950/40 border border-orange-700 px-4 py-2 text-orange-300 text-sm">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          STUB MODE — LFS simulated
        </div>
      )}

      <div className="flex items-center justify-between rounded-lg bg-slate-800 border border-slate-700 px-4 py-3">
        <span className="text-sm text-slate-400">3D Gaussian Splatting training</span>
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
        disabled={isRunning || !currentProjectId}
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
              <Line
                yAxisId="psnr"
                type="monotone"
                dataKey="psnr"
                stroke="#00D4FF"
                dot={false}
                strokeWidth={1.5}
                name="PSNR (dB)"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Control buttons */}
      {isRunning && pipelineRunning && currentProjectId && (
        <div className="flex gap-2">
          {!paused ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleControl('pause')}
              className="gap-1 border-slate-600 text-slate-300 hover:text-slate-100"
            >
              <Pause className="w-4 h-4" />
              Pause
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleControl('resume')}
              className="gap-1 border-slate-600 text-slate-300 hover:text-slate-100"
            >
              <Play className="w-4 h-4" />
              Resume
            </Button>
          )}
          <Button
            variant="destructive"
            size="sm"
            onClick={() => handleControl('abort')}
            className="gap-1"
          >
            <Square className="w-4 h-4" />
            Abort
          </Button>
        </div>
      )}

      {isDone && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-green-400 font-medium">Training complete</span>
          <Button
            onClick={() => setCurrentStep(5)}
            className="bg-cyan-600 hover:bg-cyan-500 text-white gap-1"
          >
            Proceed to Export
          </Button>
        </div>
      )}
    </div>
  );
};

export default Step4_LFS;
