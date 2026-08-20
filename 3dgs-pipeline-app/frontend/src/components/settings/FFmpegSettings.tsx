import React from 'react';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Input } from '@/components/ui/input';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Separator } from '@/components/ui/separator';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Info, TriangleAlert } from 'lucide-react';
import type { CapturePreset, ExtractDefaults } from '@/types';

interface FFmpegSettingsProps {
  settings: ExtractDefaults;
  presets: CapturePreset[];
  onChange: (s: ExtractDefaults) => void;
  /** Resolved working fps for this project's source, from /api/defaults/fps-preview. */
  fpsExplanation?: string;
}

const FFmpegSettings: React.FC<FFmpegSettingsProps> = ({
  settings,
  presets,
  onChange,
  fpsExplanation,
}) => {
  const update = <K extends keyof ExtractDefaults>(key: K, value: ExtractDefaults[K]) => {
    onChange({ ...settings, [key]: value });
  };

  const activePreset = presets.find((p) => p.id === settings.capture_preset);

  return (
    <div className="space-y-6">
      {/* Capture preset */}
      <div className="space-y-2">
        <Label>Capture preset</Label>
        <Select
          value={settings.capture_preset}
          onValueChange={(v) => update('capture_preset', v)}
        >
          <SelectTrigger className="bg-slate-950 border-slate-700 text-slate-100">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-slate-800 border-slate-700 text-slate-100">
            {presets.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {activePreset && <p className="text-xs text-slate-500">{activePreset.notes}</p>}
      </div>

      <Separator className="bg-slate-700/50" />

      {/* fps policy */}
      <div className="space-y-2">
        <Label>Working fps</Label>
        <RadioGroup
          value={settings.fps_mode}
          onValueChange={(v) => update('fps_mode', v as ExtractDefaults['fps_mode'])}
          className="flex flex-row gap-4"
        >
          {[
            { value: 'auto', label: 'Auto' },
            { value: 'ratio', label: 'Ratio' },
            { value: 'absolute', label: 'Absolute' },
          ].map((o) => (
            <div key={o.value} className="flex items-center gap-1.5">
              <RadioGroupItem value={o.value} id={`fpsmode-${o.value}`} />
              <Label htmlFor={`fpsmode-${o.value}`} className="text-slate-400 cursor-pointer">
                {o.label}
              </Label>
            </div>
          ))}
        </RadioGroup>

        {settings.fps_mode === 'auto' && (
          <div className="flex items-center gap-2 pt-1">
            <Label className="text-slate-400 w-40">Target frame count</Label>
            <Input
              type="number"
              min={10}
              step={10}
              value={settings.target_frame_count}
              onChange={(e) => update('target_frame_count', Number(e.target.value))}
              className="w-28 bg-slate-950 border-slate-700 text-slate-100"
            />
          </div>
        )}
        {settings.fps_mode === 'ratio' && (
          <div className="flex items-center gap-2 pt-1">
            <Label className="text-slate-400 w-40">Ratio of source fps</Label>
            <Input
              type="number"
              min={0.01}
              step={0.05}
              value={settings.fps_ratio}
              onChange={(e) => update('fps_ratio', Number(e.target.value))}
              className="w-28 bg-slate-950 border-slate-700 text-slate-100"
            />
          </div>
        )}
        {settings.fps_mode === 'absolute' && (
          <div className="flex items-center gap-2 pt-1">
            <Label className="text-slate-400 w-40">Frames per second</Label>
            <Input
              type="number"
              min={0.1}
              step={0.5}
              value={settings.fps_absolute}
              onChange={(e) => update('fps_absolute', Number(e.target.value))}
              className="w-28 bg-slate-950 border-slate-700 text-slate-100"
            />
          </div>
        )}

        {fpsExplanation && (
          <p className="text-xs text-cyan-400 font-mono bg-slate-950 border border-slate-800 rounded px-2 py-1.5">
            {fpsExplanation}
          </p>
        )}
      </div>

      <Separator className="bg-slate-700/50" />

      {/* mpdecimate */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5 pr-4">
          <div className="flex items-center gap-1.5">
            <Label>Remove duplicate frames</Label>
            <span
              title="mpdecimate drops frames non-deterministically, so frame indices stop matching timecodes. Leave off when curation runs."
              className="text-slate-500 hover:text-slate-300 cursor-help"
            >
              <Info className="h-3.5 w-3.5" />
            </span>
          </div>
          <p className="text-xs text-slate-500">mpdecimate filter — off by default</p>
        </div>
        <div className="flex items-center gap-2">
          {settings.mpdecimate && (
            <span className="flex items-center gap-1 text-xs text-amber-400">
              <TriangleAlert className="h-3.5 w-3.5" />
              breaks curation
            </span>
          )}
          <Switch
            checked={settings.mpdecimate}
            onCheckedChange={(v) => update('mpdecimate', v)}
          />
        </div>
      </div>

      <Separator className="bg-slate-700/50" />

      {/* JPEG quality */}
      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <Label>Quality (lower = better)</Label>
          <span className="text-sm text-cyan-400 font-mono">{settings.quality}</span>
        </div>
        <Slider
          min={1}
          max={5}
          step={1}
          value={[settings.quality]}
          onValueChange={([v]) => update('quality', v)}
        />
        <div className="flex justify-between text-xs text-slate-500">
          <span>1 (best)</span>
          <span>5 (worst)</span>
        </div>
      </div>

      <Separator className="bg-slate-700/50" />

      {/* Max frames */}
      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <Label>Max frames</Label>
          <span className="text-sm text-cyan-400 font-mono">
            {settings.max_frames === 0 ? 'Unlimited' : settings.max_frames}
          </span>
        </div>
        <Slider
          min={0}
          max={2000}
          step={50}
          value={[settings.max_frames]}
          onValueChange={([v]) => update('max_frames', v)}
        />
        <div className="flex justify-between text-xs text-slate-500">
          <span>0 = Unlimited</span>
          <span>2000</span>
        </div>
      </div>
    </div>
  );
};

export default FFmpegSettings;
