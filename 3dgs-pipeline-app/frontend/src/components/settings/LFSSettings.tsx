import React from 'react';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Separator } from '@/components/ui/separator';
import { Info } from 'lucide-react';
import { StubToggle } from './StubToggle';
import { useSettings } from '@/hooks/useSettings';
import type { LFSSettingsType } from '@/types';

interface LFSSettingsProps {
  settings: LFSSettingsType;
  onChange: (s: LFSSettingsType) => void;
}

// The strategies LichtFeld Studio v0.5.3 accepts on --strategy. "Default" sends
// no flag at all and leaves the choice to the build, which currently means MRNF.
const STRATEGIES: { value: LFSSettingsType['strategy']; label: string; hint: string }[] = [
  {
    value: 'default',
    label: 'Default (build choice)',
    hint: 'No --strategy flag — LichtFeld Studio v0.5.3 picks MRNF.',
  },
  {
    value: 'mrnf',
    label: 'MRNF',
    hint: 'Multi-Resolution Neural Field refinement — the v0.5.3 default, pinned explicitly.',
  },
  {
    value: 'mcmc',
    label: 'MCMC',
    hint: 'Markov Chain Monte Carlo — fixed Gaussian budget, slower.',
  },
  {
    value: 'igs+',
    label: 'IGS+',
    hint: 'Improved Gaussian Splatting densification.',
  },
];

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
          {STRATEGIES.map(({ value, label, hint }) => (
            <div key={value} className="flex items-center gap-2">
              <RadioGroupItem value={value} id={`strategy-${value}`} />
              <Label
                htmlFor={`strategy-${value}`}
                className="text-slate-400 cursor-pointer"
              >
                {label}
              </Label>
              <span
                title={hint}
                className="text-slate-500 hover:text-slate-300 cursor-help"
              >
                <Info className="h-3.5 w-3.5" />
              </span>
            </div>
          ))}
        </RadioGroup>
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
