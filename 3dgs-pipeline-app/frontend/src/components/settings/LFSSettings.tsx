import React from 'react';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Info } from 'lucide-react';
import { StubToggle } from './StubToggle';
import { useSettings } from '@/hooks/useSettings';
import type { LFSSettingsType } from '@/types';

interface LFSSettingsProps {
  settings: LFSSettingsType;
  onChange: (s: LFSSettingsType) => void;
}

const LFSSettings: React.FC<LFSSettingsProps> = ({ settings, onChange }) => {
  const { updateSettings } = useSettings();

  const update = <K extends keyof LFSSettingsType>(key: K, value: LFSSettingsType[K]) => {
    onChange({ ...settings, [key]: value });
  };

  const handleStubChange = (enabled: boolean) => {
    update('stub_enabled', enabled);
    updateSettings({ stubs: { lfs_stub: enabled } as never });
  };

  const handleStubDurationChange = (duration: number) => {
    update('stub_duration', duration);
    updateSettings({ stubs: { lfs_stub_duration_seconds: duration } as never });
  };

  return (
    <div className="space-y-6">
      {/* Iterations */}
      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <Label>Iterations</Label>
          <span className="text-sm text-cyan-400 font-mono">
            {settings.iterations.toLocaleString()}
          </span>
        </div>
        <Slider
          min={5000}
          max={100000}
          step={1000}
          value={[settings.iterations]}
          onValueChange={([v]) => update('iterations', v)}
        />
        <div className="flex justify-between text-xs text-slate-500">
          <span>5,000</span>
          <span>100,000</span>
        </div>
      </div>

      <Separator className="bg-slate-700/50" />

      {/* Strategy */}
      <div className="space-y-2">
        <Label>Training strategy</Label>
        <RadioGroup
          value={settings.strategy}
          onValueChange={(v) => update('strategy', v as LFSSettingsType['strategy'])}
          className="flex flex-col gap-2"
        >
          <div className="flex items-center gap-1.5">
            <RadioGroupItem value="default" id="strategy-default" />
            <Label htmlFor="strategy-default" className="text-slate-400 cursor-pointer">
              Default
            </Label>
          </div>
          <div className="flex items-center gap-2">
            <RadioGroupItem value="mcmc" id="strategy-mcmc" />
            <Label htmlFor="strategy-mcmc" className="text-slate-400 cursor-pointer">
              MCMC
            </Label>
            <span
              title="Markov Chain Monte Carlo — better quality, slower"
              className="text-slate-500 hover:text-slate-300 cursor-help"
            >
              <Info className="h-3.5 w-3.5" />
            </span>
          </div>
        </RadioGroup>
      </div>

      <Separator className="bg-slate-700/50" />

      {/* Learning rate */}
      <div className="space-y-2">
        <Label htmlFor="lfs-lr">Learning rate</Label>
        <Input
          id="lfs-lr"
          type="number"
          min={0.0001}
          max={0.01}
          step={0.0001}
          value={settings.lr}
          onChange={(e) => update('lr', Number(e.target.value))}
        />
      </div>

      <Separator className="bg-slate-700/50" />

      {/* Save interval */}
      <div className="space-y-2">
        <Label htmlFor="lfs-save-interval">Save interval</Label>
        <Input
          id="lfs-save-interval"
          type="number"
          min={0}
          max={10000}
          step={100}
          value={settings.save_interval}
          onChange={(e) => update('save_interval', Number(e.target.value))}
        />
        <p className="text-xs text-slate-500">0 = disabled</p>
      </div>

      <Separator className="bg-slate-700/50" />

      {/* Render mode */}
      <div className="space-y-2">
        <Label>Render mode</Label>
        <Select value={settings.render_mode} onValueChange={(v) => update('render_mode', v)}>
          <SelectTrigger>
            <SelectValue placeholder="Select render mode" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="RGB">RGB</SelectItem>
            <SelectItem value="RGB_D">RGB_D</SelectItem>
            <SelectItem value="DEPTH">DEPTH</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Separator className="bg-slate-700/50" />

      {/* Eval mode */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label>Eval mode</Label>
          <p className="text-xs text-slate-500">Enable evaluation metrics</p>
        </div>
        <Switch
          checked={settings.eval}
          onCheckedChange={(v) => update('eval', v)}
        />
      </div>

      {/* Save eval images (only enabled if eval=true) */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label className={settings.eval ? '' : 'opacity-50'}>Save eval images</Label>
          <p className="text-xs text-slate-500">Requires eval mode enabled</p>
        </div>
        <Switch
          checked={settings.save_eval_images}
          onCheckedChange={(v) => update('save_eval_images', v)}
          disabled={!settings.eval}
        />
      </div>

      <Separator className="bg-slate-700/50" />

      {/* Background color */}
      <div className="space-y-2">
        <Label htmlFor="lfs-bg-color">Background color</Label>
        <div className="flex items-center gap-3">
          <input
            id="lfs-bg-color"
            type="color"
            value={settings.background_color}
            onChange={(e) => update('background_color', e.target.value)}
            className="h-9 w-14 rounded-md border border-slate-700 bg-slate-800 cursor-pointer p-1"
          />
          <span className="text-sm text-cyan-400 font-mono">{settings.background_color}</span>
        </div>
      </div>

      {/* DEV stub section */}
      <StubToggle
        tool="LichtFeld Studio"
        enabled={settings.stub_enabled}
        onChange={handleStubChange}
        durationSeconds={settings.stub_duration}
        onDurationChange={handleStubDurationChange}
      />
    </div>
  );
};

export default LFSSettings;
