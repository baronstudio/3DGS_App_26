import React, { useState } from 'react';
import { Settings, ChevronRight, AlertTriangle, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePipelineStore } from '@/store/pipelineStore';
import { usePipeline } from '@/hooks/usePipeline';
import { useSettings } from '@/hooks/useSettings';
import { ProgressBar } from '@/components/panels/ProgressBar';
import RCSettings from '@/components/settings/RCSettings';
import type { RCSettingsType } from '@/types';

const DEFAULT_RC: RCSettingsType = {
  precision: 'Normal',
  max_features: 60000,
  keep_largest: true,
  stub_enabled: false,
  stub_duration: 10,
};

function parseRCStats(logs: { message: string; level: string }[]): { cameras: number | null; points: number | null } {
  const PATTERN = /Aligned\s+(\d+)\s+cameras?,\s+(\d+)\s+points?/i;
  for (let i = logs.length - 1; i >= 0; i--) {
    const m = logs[i].message.match(PATTERN);
    if (m) return { cameras: parseInt(m[1], 10), points: parseInt(m[2], 10) };
  }
  return { cameras: null, points: null };
}

const Step3_RC: React.FC = () => {
  const { currentProjectId, stepStatuses, logs, setCurrentStep } = usePipelineStore();
  const { startPipeline } = usePipeline();
  const { settings } = useSettings();
  const [showSettings, setShowSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rcSettings, setRcSettings] = useState<RCSettingsType>(DEFAULT_RC);

  const status = stepStatuses[3];  // step 3 = rc
  const isRunning = status === 'running';
  const isDone = status === 'done';
  const isStub = settings?.stubs?.rc_stub ?? false;

  const rcLogs = logs.filter((l) => l.step === 'rc');
  const { cameras, points } = parseRCStats(rcLogs);

  const handleRun = async () => {
    if (!currentProjectId) return;
    setError(null);
    try {
      await startPipeline(currentProjectId, 3, {});
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start RC alignment';
      setError(msg);
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-2xl mx-auto">
      <h2 className="text-xl font-semibold text-slate-100">Step 3 — RealityCapture Alignment</h2>

      {isStub && (
        <div className="flex items-center gap-2 rounded-md bg-orange-950/40 border border-orange-700 px-4 py-2 text-orange-300 text-sm">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          STUB MODE — RC simulated
        </div>
      )}

      <div className="flex items-center justify-between rounded-lg bg-slate-800 border border-slate-700 px-4 py-3">
        <span className="text-sm text-slate-400">RealityCapture alignment &amp; sparse reconstruction</span>
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
          <RCSettings settings={rcSettings} onChange={setRcSettings} />
        </div>
      )}

      {error && (
        <p className="text-sm text-red-400 bg-red-950/30 border border-red-800 rounded px-3 py-2">
          {error}
        </p>
      )}

      <Button
        onClick={handleRun}
        disabled={isRunning || !currentProjectId}
        className="bg-cyan-600 hover:bg-cyan-500 text-white"
      >
        {isRunning ? 'Aligning…' : 'Run Alignment'}
      </Button>

      {(isRunning || isDone) && (
        <ProgressBar step="rc" label="RC Alignment" />
      )}

      {isDone && (cameras !== null || points !== null) && (
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg bg-slate-800 border border-slate-700 px-4 py-3 text-center">
            <p className="text-2xl font-bold text-cyan-400">{cameras ?? '—'}</p>
            <p className="text-xs text-slate-400">Aligned cameras</p>
          </div>
          <div className="rounded-lg bg-slate-800 border border-slate-700 px-4 py-3 text-center">
            <p className="text-2xl font-bold text-cyan-400">{points !== null ? points.toLocaleString() : '—'}</p>
            <p className="text-xs text-slate-400">Sparse points</p>
          </div>
        </div>
      )}

      {isDone && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-green-400 font-medium">Alignment complete</span>
          <Button
            onClick={() => setCurrentStep(4)}
            className="bg-green-700 hover:bg-green-600 text-white gap-1"
          >
            <CheckCircle className="w-4 h-4" />
            Validate &amp; Continue to LFS Training
          </Button>
        </div>
      )}
    </div>
  );
};

export default Step3_RC;
