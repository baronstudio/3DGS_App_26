import React from 'react';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import type { RCImageOverlap, RCSettingsType } from '@/types';

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

const OVERLAP_OPTIONS: Array<{ value: RCImageOverlap; hint: string }> = [
  { value: 'Low', hint: 'below 20 %' },
  { value: 'Medium', hint: 'the usual' },
  { value: 'High', hint: 'above 60 %' },
];

const RCSettings: React.FC<RCSettingsProps> = ({ settings, onChange }) => {
  const update = <K extends keyof RCSettingsType>(key: K, value: RCSettingsType[K]) => {
    onChange({ ...settings, [key]: value });
  };

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

      {/* Custom .rsbox file */}
      <div className="space-y-2">
        <Label htmlFor="rsbox-path">Custom .rsbox file</Label>
        <Input
          id="rsbox-path"
          type="file"
          accept=".rsbox"
          className="cursor-pointer"
          onChange={(e) => {
            const file = e.target.files?.[0];
            update('rsbox_path', file ? file.name : undefined);
          }}
        />
        <p className="text-xs text-slate-500">Optional — leave empty to use default</p>
      </div>
    </div>
  );
};

export default RCSettings;
