import React, { useEffect, useRef, useState } from 'react';
import { usePipelineStore } from '../../store/pipelineStore';

interface ProgressSample {
  ts: number;
  progress: number;
}

interface ProgressBarProps {
  step: string;
  label: string;
}

function formatEta(seconds: number): string {
  if (seconds < 10) return 'Almost done…';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m > 0 ? `~${m}m ${s}s remaining` : `~${s}s remaining`;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ step, label }) => {
  const progress = usePipelineStore((s) => s.stepProgress[step] ?? 0);
  const stepStatuses = usePipelineStore((s) => s.stepStatuses);

  // Determine visual state
  const isError = Object.values(stepStatuses).some(
    (_, i) => Object.keys(stepStatuses)[i] && stepStatuses[Number(Object.keys(stepStatuses)[i])] === 'error'
  );

  // Derive active step status from store by step name mapping
  const stepNameToIndex: Record<string, number> = {
    extract: 1, rc: 2, lfs: 3, export: 4, blender: 5,
  };
  const stepIndex = stepNameToIndex[step];
  const stepStatus = stepIndex !== undefined ? stepStatuses[stepIndex] : undefined;
  const isDone = stepStatus === 'done';
  const isStepError = stepStatus === 'error';

  // ETA estimation via progress samples
  const samplesRef = useRef<ProgressSample[]>([]);
  const [eta, setEta] = useState<string | null>(null);

  useEffect(() => {
    if (progress <= 0.05) {
      samplesRef.current = [];
      setEta(null);
      return;
    }
    if (progress >= 0.99) {
      setEta(null);
      return;
    }
    const now = Date.now();
    samplesRef.current.push({ ts: now, progress });
    // Keep only the last 20 samples
    if (samplesRef.current.length > 20) {
      samplesRef.current = samplesRef.current.slice(-20);
    }
    const first = samplesRef.current[0];
    const elapsed = (now - first.ts) / 1000; // seconds
    const progressDelta = progress - first.progress;
    if (progressDelta > 0.001 && elapsed > 0) {
      const remaining = (elapsed / progressDelta) * (1 - progress);
      setEta(formatEta(remaining));
    }
  }, [progress]);

  const pct = Math.round(progress * 100);

  const trackColor = isStepError
    ? 'bg-red-500/20'
    : isDone
    ? 'bg-green-500/20'
    : 'bg-cyan-500/20';

  const fillColor = isStepError
    ? 'bg-red-500'
    : isDone
    ? 'bg-green-500'
    : 'bg-cyan-500';

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-slate-300">{label}</span>
        <div className="flex items-center gap-2">
          {eta && (
            <span className="text-xs text-slate-500 italic">{eta}</span>
          )}
          <span className="text-xs font-mono text-slate-400">{pct}%</span>
        </div>
      </div>
      <div className={`w-full h-2 rounded-full ${trackColor}`}>
        <div
          className={`h-2 rounded-full transition-all duration-300 ${fillColor}`}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
    </div>
  );
};

export default ProgressBar;

