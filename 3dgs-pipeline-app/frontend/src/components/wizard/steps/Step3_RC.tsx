import React, { useCallback, useEffect, useState } from 'react';
import { Settings, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import client from '@/api/client';
import { usePipelineStore } from '@/store/pipelineStore';
import { usePipeline } from '@/hooks/usePipeline';
import { useDefaults } from '@/hooks/useDefaults';
import { useProjectSettings } from '@/hooks/useProjectSettings';
import { ProgressBar } from '@/components/panels/ProgressBar';
import SceneViewer from '@/components/viewer/SceneViewer';
import RCSettings from '@/components/settings/RCSettings';
import SaveState from '@/components/settings/SaveState';
import type { AlignmentReport, RCDefaults, RCSettingsType } from '@/types';

/** Cameras / points from the RC log. */
function parseRCStats(logs: { message: string; level: string }[]): { cameras: number | null; points: number | null } {
  const PATTERNS = [
    /Aligned\s+(\d+)\s+cameras?,\s+([\d,]+)\s+points?/i,
    /Cameras aligned:\s*(\d+)\s*\/\s*\d+\s*\|\s*Sparse points:\s*([\d,]+)/i,
  ];
  for (let i = logs.length - 1; i >= 0; i--) {
    for (const pattern of PATTERNS) {
      const m = logs[i].message.match(pattern);
      if (m) {
        return {
          cameras: parseInt(m[1], 10),
          points: parseInt(m[2].replace(/,/g, ''), 10),
        };
      }
    }
  }
  return { cameras: null, points: null };
}

const Step3_RC: React.FC = () => {
  const { currentProjectId, stepStatuses, logs, setCurrentStep } = usePipelineStore();
  const { startPipeline } = usePipeline();
  const { defaults } = useDefaults();
  const [showSettings, setShowSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [alignment, setAlignment] = useState<AlignmentReport | null>(null);

  // defaults.json under this project's overrides, saved on every change
  // (CLAUDE.md §4). `rc` is deep: `colmap` and its `undistort` block are edited
  // from the setup panel and must survive a change made here.
  const {
    value: rcSettings, setValue: setRcSettings, flush: flushRc,
    saving, savedAt, error: saveError,
  } = useProjectSettings<RCDefaults>(currentProjectId, 'rc', defaults?.rc ?? null);

  const status = stepStatuses[3];  // step 3 = rc
  const isRunning = status === 'running';
  const isDone = status === 'done';

  const rcLogs = logs.filter((l) => l.step === 'rc');
  const { cameras, points } = parseRCStats(rcLogs);

  const fetchAlignment = useCallback(async () => {
    if (!currentProjectId) return;
    try {
      const res = await client.get<{ alignment: AlignmentReport | null }>(
        `/files/${currentProjectId}/alignment`,
      );
      setAlignment(res.data.alignment);
    } catch {
      setAlignment(null);
    }
  }, [currentProjectId]);

  // On mount and whenever the step finishes: the report is a file, not a log line.
  useEffect(() => {
    if (isRunning) return;
    fetchAlignment();
  }, [fetchAlignment, isRunning, isDone]);

  const handleRun = async () => {
    if (!currentProjectId || !rcSettings) return;
    setError(null);
    setAlignment(null);
    try {
      await flushRc();  // land any debounced edit before the run reads the row
      await startPipeline(currentProjectId, 3, { rc: rcSettings });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start RS alignment';
      setError(msg);
    }
  };

  const split = alignment?.checked === true && alignment.missing_count > 0;
  const affectedSequences = (alignment?.sequences ?? []).filter((s) => s.missing > 0);

  return (
    <div className="flex flex-col gap-6 p-6 max-w-2xl mx-auto">
      <h2 className="text-xl font-semibold text-slate-100">Step 3 — RealityScan Alignment</h2>

      <div className="flex items-center justify-between rounded-lg bg-slate-800 border border-slate-700 px-4 py-3">
        <span className="text-sm text-slate-400">RealityScan alignment &amp; sparse reconstruction</span>
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

      {showSettings && rcSettings && (
        <div className="rounded-lg bg-slate-800 border border-slate-700 p-4">
          {/* The panel edits a subset of RCDefaults; spread it back over the
              whole block so `colmap` and `normalise_for_lfs` are not dropped. */}
          <RCSettings
            settings={rcSettings}
            onChange={(s: RCSettingsType) => setRcSettings({ ...rcSettings, ...s })}
          />
        </div>
      )}

      {error && (
        <p className="text-sm text-red-400 bg-red-950/30 border border-red-800 rounded px-3 py-2">
          {error}
        </p>
      )}

      <Button
        onClick={handleRun}
        disabled={isRunning || !currentProjectId || !rcSettings}
        className="bg-cyan-600 hover:bg-cyan-500 text-white"
      >
        {isRunning ? 'Aligning…' : 'Run Alignment'}
      </Button>

      {(isRunning || isDone) && (
        <ProgressBar step="rc" label="RS Alignment" />
      )}

      {isDone && (cameras !== null || points !== null) && (
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg bg-slate-800 border border-slate-700 px-4 py-3 text-center">
            <p className="text-2xl font-bold text-cyan-400">
              {alignment?.checked ? alignment.aligned_count : (cameras ?? '—')}
            </p>
            <p className="text-xs text-slate-400">Aligned cameras</p>
          </div>
          <div className="rounded-lg bg-slate-800 border border-slate-700 px-4 py-3 text-center">
            <p className="text-2xl font-bold text-cyan-400">{points !== null ? points.toLocaleString() : '—'}</p>
            <p className="text-xs text-slate-400">Sparse points</p>
          </div>
        </div>
      )}

      {/* Alignment coverage — what we fed RC vs what came back registered.
          A split alignment is dropped silently by -selectMaximalComponent; this
          panel is the only place it becomes visible (CLAUDE.md §7). */}
      {alignment?.checked && (
        <div
          className={`rounded-lg border px-4 py-3 space-y-2 ${
            split
              ? 'bg-amber-950/30 border-amber-700'
              : 'bg-slate-800 border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-200">Alignment coverage</span>
            <span className={`text-sm font-mono ${split ? 'text-amber-300' : 'text-green-400'}`}>
              {alignment.aligned_count}/{alignment.input_count}
              {alignment.aligned_ratio !== null && ` · ${(alignment.aligned_ratio * 100).toFixed(1)}%`}
            </span>
          </div>

          {!split && (
            <p className="text-xs text-slate-400">
              Single component — every frame landed in one coordinate frame.
            </p>
          )}

          {split && (
            <div className="space-y-2 text-xs text-amber-200/90">
              <p>
                {alignment.missing_count} frame{alignment.missing_count > 1 ? 's' : ''} ended up in
                another component and {alignment.missing_count > 1 ? 'are' : 'is'} absent from the
                exported registration. LichtFeld will train on that component only.
              </p>

              {affectedSequences.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {affectedSequences.map((s) => (
                    <span
                      key={s.sequence_id}
                      className="rounded bg-amber-900/50 border border-amber-700/60 px-2 py-0.5 font-mono"
                    >
                      seq #{s.sequence_id}: {s.missing}/{s.input} missing
                    </span>
                  ))}
                </div>
              )}

              <p className="text-amber-200/70">
                Re-align with a higher image overlap, keep the frames the overlap gate rejected
                around the cuts, or merge the components with control points in the RealityScan GUI.
              </p>

              {alignment.missing_frames.length > 0 && (
                <details>
                  <summary className="cursor-pointer text-amber-300 hover:text-amber-200">
                    Show missing frames
                  </summary>
                  <p className="mt-1 font-mono text-[11px] leading-relaxed text-amber-200/70 break-all">
                    {alignment.missing_frames.join(', ')}
                  </p>
                </details>
              )}
            </div>
          )}
        </div>
      )}

      {/* Sparse cloud + registered cameras. A bad alignment — a fold in the
          camera path, a component sitting at another scale — is visible here
          and nowhere in the numbers above. */}
      {currentProjectId && !isRunning && (
        <div className="rounded-lg bg-slate-800 border border-slate-700 p-3 space-y-2">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">
            Sparse cloud
          </p>
          {/* The region editor is offered here and nowhere else: the
              Reconstruction Region is an input to RealityScan, so steps 4 and 5
              have no business growing a box gizmo. */}
          <SceneViewer
            projectId={currentProjectId}
            source="rc"
            refreshKey={status}
            withRegion={(rcSettings?.region?.mode ?? 'auto') !== 'off'}
            height={440}
          />
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
