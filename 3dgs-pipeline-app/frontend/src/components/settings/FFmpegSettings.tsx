import React from 'react';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Separator } from '@/components/ui/separator';
import { Info } from 'lucide-react';
import type { FFmpegSettingsType } from '@/types';

interface FFmpegSettingsProps {
  settings: FFmpegSettingsType;
  onChange: (s: FFmpegSettingsType) => void;
}

const FPS_OPTIONS = [0.5, 1, 2, 3, 5];

const FFmpegSettings: React.FC<FFmpegSettingsProps> = ({ settings, onChange }) => {
  const update = <K extends keyof FFmpegSettingsType>(key: K, value: FFmpegSettingsType[K]) => {
    onChange({ ...settings, [key]: value });
  };

  return (
    <div className="space-y-6">
      {/* FPS */}
      <div className="space-y-2">
        <Label>Frames per second</Label>
        <RadioGroup
          value={String(settings.fps)}
          onValueChange={(v) => update('fps', Number(v))}
          className="flex flex-row gap-3"
        >
          {FPS_OPTIONS.map((fps) => (
            <div key={fps} className="flex items-center gap-1.5">
              <RadioGroupItem value={String(fps)} id={`fps-${fps}`} />
              <Label htmlFor={`fps-${fps}`} className="text-slate-400 cursor-pointer">
                {fps}
              </Label>
            </div>
          ))}
        </RadioGroup>
      </div>

      <Separator className="bg-slate-700/50" />

      {/* mpdecimate */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <div className="flex items-center gap-1.5">
            <Label>Remove duplicate frames</Label>
            <span
              title="Removes duplicate frames — recommended"
              className="text-slate-500 hover:text-slate-300 cursor-help"
            >
              <Info className="h-3.5 w-3.5" />
            </span>
          </div>
          <p className="text-xs text-slate-500">mpdecimate filter</p>
        </div>
        <Switch
          checked={settings.mpdecimate}
          onCheckedChange={(v) => update('mpdecimate', v)}
        />
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
          max={500}
          step={10}
          value={[settings.max_frames]}
          onValueChange={([v]) => update('max_frames', v)}
        />
        <div className="flex justify-between text-xs text-slate-500">
          <span>0 = Unlimited</span>
          <span>500</span>
        </div>
      </div>
    </div>
  );
};

export default FFmpegSettings;
