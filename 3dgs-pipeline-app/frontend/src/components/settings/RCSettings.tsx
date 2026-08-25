import React from 'react';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Separator } from '@/components/ui/separator';
import type {
  MaskGenerationDefaults, RCImageOverlap, RCSettingsType, RegionDefaults,
} from '@/types';

interface RCSettingsProps {
  settings: RCSettingsType;
  onChange: (s: RCSettingsType) => void;
}

// RealityScan 2.2 has two feature-detection qualities, not three: Normal and
// High (Help → Alignment Settings). The "Preview" this radio used to offer
// existed nowhere in RS.
const QUALITY_OPTIONS: Array<{ value: RCSettingsType['feature_detection_quality']; label: string }> = [
  { value: 'Normal', label: 'Normal' },
  { value: 'High', label: 'High' },
];

// RS exports nothing unless a region exists, and the region has to be set
// *after* -align: ByDensity reads the sparse cloud.
const REGION_OPTIONS: Array<{ value: RegionDefaults['mode']; label: string; hint: string }> = [
  { value: 'auto', label: 'Automatic', hint: 'a box around the whole component' },
  { value: 'density', label: 'By density', hint: 'hugs the densest part of the sparse cloud' },
  { value: 'off', label: 'Off', hint: 'no region, and no box to edit' },
];

const DEFAULT_REGION: RegionDefaults = { mode: 'auto', scale: [1, 1, 1], export: true };

const DEFAULT_MASKS: MaskGenerationDefaults = {
  enabled: false,
  mesh_quality: 'preview',
  use_region: true,
  save_project_after: true,
  preview_downscale: 4,
  normal_downscale: 2,
  gpu_acceleration: true,
};

// What each quality costs. Measured on publicsemple_truck, 251 images of about
// one megapixel; the ratios are what carry over, not the seconds.
const MESH_OPTIONS: Array<{
  value: MaskGenerationDefaults['mesh_quality']; label: string; hint: string;
}> = [
  { value: 'preview', label: 'Preview', hint: 'seconds — enough for a silhouette' },
  { value: 'normal', label: 'Normal', hint: 'minutes' },
  { value: 'high', label: 'High', hint: 'long, and a mask does not need it' },
];

const OVERLAP_OPTIONS: Array<{ value: RCImageOverlap; hint: string }> = [
  { value: 'Low', hint: 'below 20 %' },
  { value: 'Medium', hint: 'the usual' },
  { value: 'High', hint: 'above 60 %' },
];

const RCSettings: React.FC<RCSettingsProps> = ({ settings, onChange }) => {
  const update = <K extends keyof RCSettingsType>(key: K, value: RCSettingsType[K]) => {
    onChange({ ...settings, [key]: value });
  };

  // The panel edits a subset of RCDefaults and is mounted before the fetch
  // lands in one of its two homes, so the block is defaulted rather than
  // assumed present.
  const region = settings.region ?? DEFAULT_REGION;
  const setRegion = (next: RegionDefaults) => update('region', next);
  const masks = settings.masks ?? DEFAULT_MASKS;
  const setMasks = (next: MaskGenerationDefaults) => update('masks', next);

  return (
    <div className="space-y-6">
      {/* Feature detection quality — RS's sfmFeatureDetectionQuality */}
      <div className="space-y-2">
        <Label>Feature detection quality</Label>
        <RadioGroup
          value={settings.feature_detection_quality}
          onValueChange={(v) =>
            update('feature_detection_quality', v as RCSettingsType['feature_detection_quality'])
          }
          className="flex flex-row gap-4"
        >
          {QUALITY_OPTIONS.map(({ value, label }) => (
            <div key={value} className="flex items-center gap-1.5">
              <RadioGroupItem value={value} id={`quality-${value}`} />
              <Label htmlFor={`quality-${value}`} className="text-slate-400 cursor-pointer">
                {label}
              </Label>
            </div>
          ))}
        </RadioGroup>
        <p className="text-xs text-slate-500">
          High detects more features and aligns more precisely, for more time and RAM.
        </p>
      </div>

      <Separator className="bg-slate-700/50" />

      {/* Max features per image */}
      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <Label>Max features per image</Label>
          <span className="text-sm text-cyan-400 font-mono">
            {settings.max_features.toLocaleString()}
          </span>
        </div>
        <Slider
          min={40000}
          max={80000}
          step={1000}
          value={[settings.max_features]}
          onValueChange={([v]) => update('max_features', v)}
        />
        <div className="flex justify-between text-xs text-slate-500">
          <span>40,000</span>
          <span>80,000</span>
        </div>
      </div>

      <Separator className="bg-slate-700/50" />

      {/* Image overlap — how much neighbouring frames share. §7.1: this is what
          has to carry the match across a cut, where the sequential preselection
          has nothing to work with. */}
      <div className="space-y-2">
        <Label>Image overlap</Label>
        <RadioGroup
          value={settings.image_overlap}
          onValueChange={(v) => update('image_overlap', v as RCImageOverlap)}
          className="flex flex-row gap-4"
        >
          {OVERLAP_OPTIONS.map(({ value, hint }) => (
            <div key={value} className="flex items-center gap-1.5">
              <RadioGroupItem value={value} id={`overlap-${value}`} />
              <Label htmlFor={`overlap-${value}`} className="text-slate-400 cursor-pointer">
                {value} <span className="text-slate-600">({hint})</span>
              </Label>
            </div>
          ))}
        </RadioGroup>
        <p className="text-xs text-slate-500">
          How much of the object neighbouring frames share. Raise it when curation found
          several sequences — across a cut, frame k and k+1 are unrelated and the sequential
          preselection cannot bridge them.
        </p>
      </div>

      <Separator className="bg-slate-700/50" />

      {/* Components — groups are not components, see CLAUDE.md §7 */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label>Merge components</Label>
          <p className="text-xs text-slate-500">
            Tries to fuse split components before export. Turn off if your RealityScan
            build rejects <code>-mergeComponents</code>.
          </p>
        </div>
        <Switch
          checked={settings.merge_components}
          onCheckedChange={(v) => update('merge_components', v)}
        />
      </div>

      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label>Keep largest component only</Label>
          <p className="text-xs text-slate-500">
            Drops whatever did not merge. What it drops is reported after the run.
          </p>
        </div>
        <Switch
          checked={settings.keep_largest}
          onCheckedChange={(v) => update('keep_largest', v)}
        />
      </div>

      <Separator className="bg-slate-700/50" />

      {/* Reconstruction Region — the seed, not the box.
          The file input that used to sit here offered a "custom .rsbox" that
          nothing ever read: a browser file input yields a name, not a path, and
          no field of RCDefaults carried it. The box is placed in the viewer
          below and saved to projects/<slug>/region/. */}
      <div className="space-y-2">
        <Label>Reconstruction region</Label>
        <RadioGroup
          value={region.mode}
          onValueChange={(v) => setRegion({ ...region, mode: v as RegionDefaults['mode'] })}
          className="flex flex-row flex-wrap gap-4"
        >
          {REGION_OPTIONS.map(({ value, label, hint }) => (
            <div key={value} className="flex items-center gap-1.5">
              <RadioGroupItem value={value} id={`region-${value}`} />
              <Label htmlFor={`region-${value}`} className="text-slate-400 cursor-pointer">
                {label} <span className="text-slate-600">({hint})</span>
              </Label>
            </div>
          ))}
        </RadioGroup>
        <p className="text-xs text-slate-500">
          The volume RealityScan reconstructs inside — and what the masks of the next
          step are rendered from. This only seeds it: the box you validate in the
          viewer below is kept in <code>region/</code>, which a re-alignment does not
          delete.
        </p>
      </div>

      {region.mode !== 'off' && (
        <div className="space-y-2">
          <Label>Scale the fitted region</Label>
          <div className="flex items-center gap-2">
            {(['X', 'Y', 'Z'] as const).map((axis, index) => (
              <label key={axis} className="flex flex-1 items-center gap-1.5">
                <span className="text-xs text-slate-600">{axis}</span>
                <input
                  type="number"
                  step={0.05}
                  min={0.05}
                  value={region.scale[index] ?? 1}
                  onChange={(e) => {
                    const scale = [...region.scale];
                    const parsed = Number(e.target.value);
                    scale[index] = Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
                    setRegion({ ...region, scale });
                  }}
                  className="w-full min-w-0 rounded border border-slate-700 bg-slate-900 px-2 py-1
                             font-mono text-xs text-slate-200 focus:border-cyan-600 focus:outline-none"
                />
              </label>
            ))}
          </div>
          <p className="text-xs text-slate-500">
            Factors from the centre of whatever the fit produced. All ones sends no
            <code> -scaleReconstructionRegion</code> at all — a density fit hugs the
            subject, and a little air around it is usually what you want.
          </p>
        </div>
      )}

      <Separator className="bg-slate-700/50" />

      {/* Masks from the mesh — a separate RealityScan run over the saved
          project, offered after the alignment and never part of it. */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label>Generate masks</Label>
          <p className="text-xs text-slate-500">
            Offers a second RealityScan run after the alignment: a mesh inside the box
            you validate, rendered from every camera, exported into the dataset as
            <code> masks/</code>. It never re-aligns, and it is what LichtFeld Studio
            trains against with <code>--mask-mode</code>.
          </p>
        </div>
        <Switch
          checked={masks.enabled}
          onCheckedChange={(v) => setMasks({ ...masks, enabled: v })}
        />
      </div>

      {masks.enabled && (
        <>
          <div className="space-y-2">
            <Label>Mesh quality</Label>
            <RadioGroup
              value={masks.mesh_quality}
              onValueChange={(v) =>
                setMasks({ ...masks, mesh_quality: v as MaskGenerationDefaults['mesh_quality'] })
              }
              className="flex flex-row flex-wrap gap-4"
            >
              {MESH_OPTIONS.map(({ value, label, hint }) => (
                <div key={value} className="flex items-center gap-1.5">
                  <RadioGroupItem value={value} id={`mesh-${value}`} />
                  <Label htmlFor={`mesh-${value}`} className="text-slate-400 cursor-pointer">
                    {label} <span className="text-slate-600">({hint})</span>
                  </Label>
                </div>
              ))}
            </RadioGroup>
            <p className="text-xs text-slate-500">
              The mask is the mesh's outline seen from the camera, not its surface, so
              preview is normally the right answer. Everything else about this run lives
              in Setup → RealityScan.
            </p>
          </div>

          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Mesh inside the validated box</Label>
              <p className="text-xs text-slate-500">
                Sends the box saved in <code>region/</code>. Off, or with nothing saved,
                RealityScan uses the region the alignment left in the project.
              </p>
            </div>
            <Switch
              checked={masks.use_region}
              onCheckedChange={(v) => setMasks({ ...masks, use_region: v })}
            />
          </div>
        </>
      )}
    </div>
  );
};

export default RCSettings;
