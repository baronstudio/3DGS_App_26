import React from 'react';
import { Box, Crosshair, Move3d, RotateCw, Save, Scaling, Undo2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { Region } from '@/types';

/**
 * The numeric half of the Reconstruction Region editor.
 *
 * A gizmo alone cannot place a box repeatably: a box 2 cm out in Z is
 * invisible on screen and fatal to the mesh the mask is rendered from. So
 * every number the gizmo writes is also typeable, and the two edit the same
 * state.
 *
 * The values are in the app's frame (`rc_region.py`), never in RealityScan's
 * and never with the viewer's display flips applied — those live on the parent
 * group of the mesh and stop there.
 */

export type RegionMode = 'translate' | 'rotate' | 'scale' | null;

interface RegionEditorProps {
  region: Region;
  mode: RegionMode;
  onMode: (mode: RegionMode) => void;
  onChange: (region: Region) => void;
  onFit: () => void;
  onReset: () => void;
  onSave: () => void;
  /** null while the preview is still loading — the count is browser-side. */
  inside: number | null;
  total: number | null;
  dirty: boolean;
  saving: boolean;
  savedAt: number | null;
  error: string | null;
  /** True while this is RS's own box rather than something the user validated. */
  seeded: boolean;
  source: string;
  canReset: boolean;
}

const SOURCE_LABEL: Record<string, string> = {
  rsbox_auto: "RealityScan's own region",
  manual: 'Placed by hand',
  pointcloud_percentile: 'Fitted to the sparse cloud',
};

const AXES = ['X', 'Y', 'Z'] as const;

const NumberRow: React.FC<{
  label: string;
  values: number[];
  step: number;
  min?: number;
  onChange: (values: number[]) => void;
}> = ({ label, values, step, min, onChange }) => (
  <div className="flex items-center gap-2">
    <span className="w-16 shrink-0 text-xs text-slate-500">{label}</span>
    {AXES.map((axis, index) => (
      <label key={axis} className="flex flex-1 items-center gap-1">
        <span className="text-[10px] text-slate-600">{axis}</span>
        <input
          type="number"
          step={step}
          min={min}
          value={Number.isFinite(values[index]) ? Number(values[index].toFixed(4)) : 0}
          onChange={(e) => {
            const next = [...values];
            const parsed = Number(e.target.value);
            next[index] = Number.isFinite(parsed) ? parsed : values[index];
            onChange(next);
          }}
          className="w-full min-w-0 rounded border border-slate-700 bg-slate-900 px-1.5 py-1
                     font-mono text-xs text-slate-200 focus:border-cyan-600 focus:outline-none"
        />
      </label>
    ))}
  </div>
);

export const RegionEditor: React.FC<RegionEditorProps> = ({
  region, mode, onMode, onChange, onFit, onReset, onSave,
  inside, total, dirty, saving, savedAt, error, seeded, source, canReset,
}) => {
  const ratio = inside !== null && total ? inside / total : null;

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">
          <Box className="h-3.5 w-3.5" />
          Reconstruction region
        </span>

        <div className="flex items-center gap-0.5 rounded-md border border-slate-700 bg-slate-800 p-0.5">
          {([
            ['translate', Move3d, 'Move'],
            ['rotate', RotateCw, 'Rotate'],
            ['scale', Scaling, 'Resize'],
          ] as const).map(([value, Icon, title]) => (
            <button
              key={value}
              title={title}
              onClick={() => onMode(mode === value ? null : value)}
              className={`rounded px-2 py-1 transition-colors ${
                mode === value ? 'bg-cyan-600 text-white' : 'text-slate-400 hover:text-slate-100'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
            </button>
          ))}
        </div>

        <div className="flex-1" />

        <Button variant="ghost" size="sm" onClick={onFit}
                className="gap-1 text-xs text-slate-400 hover:text-slate-100"
                title="Percentile bounds of the loaded preview — never min/max, one stray point would define the whole box">
          <Crosshair className="h-3.5 w-3.5" />
          Fit to cloud
        </Button>
        <Button variant="ghost" size="sm" onClick={onReset} disabled={!canReset}
                className="gap-1 text-xs text-slate-400 hover:text-slate-100"
                title="Back to the region RealityScan exported for this alignment">
          <Undo2 className="h-3.5 w-3.5" />
          Reset to RS
        </Button>
        <Button size="sm" onClick={onSave} disabled={saving || (!dirty && !seeded)}
                className="gap-1 bg-cyan-600 text-xs text-white hover:bg-cyan-500">
          <Save className="h-3.5 w-3.5" />
          {saving ? 'Saving…' : 'Save region'}
        </Button>
      </div>

      <div className="space-y-1.5">
        <NumberRow
          label="Centre"
          values={region.centre}
          step={0.1}
          onChange={(centre) => onChange({ ...region, centre })}
        />
        <NumberRow
          label="Size"
          values={region.size}
          step={0.1}
          min={0.001}
          onChange={(size) => onChange({
            ...region,
            size: size.map((v) => Math.max(Math.abs(v), 0.001)),
          })}
        />
        <NumberRow
          label="Rotation °"
          values={region.euler_deg}
          step={1}
          onChange={(euler_deg) => onChange({ ...region, euler_deg })}
        />
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className={ratio !== null && ratio < 0.05 ? 'text-amber-400' : 'text-slate-400'}>
          {inside === null || total === null
            ? 'Counting…'
            : `${inside.toLocaleString()}/${total.toLocaleString()} preview points inside`}
          {ratio !== null && ` · ${(ratio * 100).toFixed(1)} %`}
        </span>
        <span className="text-slate-600">{SOURCE_LABEL[source] ?? source}</span>
        {seeded && !dirty && (
          <span className="text-slate-600">not saved yet — this is a proposal</span>
        )}
        {dirty && !saving && <span className="text-amber-400">unsaved changes</span>}
        {!dirty && savedAt !== null && <span className="text-green-500">saved</span>}
        <span className="text-slate-600">
          The count is over the decimated preview, not the whole cloud — the ratio is the number to read.
        </span>
      </div>

      {error && (
        <p className="rounded border border-red-800 bg-red-950/30 px-2 py-1 text-xs text-red-400">
          {error}
        </p>
      )}
    </div>
  );
};

export default RegionEditor;
