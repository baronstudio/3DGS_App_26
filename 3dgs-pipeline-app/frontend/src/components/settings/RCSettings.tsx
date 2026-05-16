import React from 'react';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import { StubToggle } from './StubToggle';
import { useSettings } from '@/hooks/useSettings';
import type { RCSettingsType } from '@/types';

interface RCSettingsProps {
  settings: RCSettingsType;
  onChange: (s: RCSettingsType) => void;
}

const PRECISION_OPTIONS: Array<{ value: RCSettingsType['precision']; label: string }> = [
  { value: 'Preview', label: 'Preview' },
  { value: 'Normal', label: 'Normal' },
  { value: 'High', label: 'High' },
];

const RCSettings: React.FC<RCSettingsProps> = ({ settings, onChange }) => {
  const { updateSettings } = useSettings();

  const update = <K extends keyof RCSettingsType>(key: K, value: RCSettingsType[K]) => {
    onChange({ ...settings, [key]: value });
  };

  const handleStubChange = (enabled: boolean) => {
    update('stub_enabled', enabled);
    updateSettings({ stubs: { rc_stub: enabled } as never });
  };

  const handleStubDurationChange = (duration: number) => {
    update('stub_duration', duration);
    updateSettings({ stubs: { rc_stub_duration_seconds: duration } as never });
  };

  return (
    <div className="space-y-6">
      {/* Alignment precision */}
      <div className="space-y-2">
        <Label>Alignment precision</Label>
        <RadioGroup
          value={settings.precision}
          onValueChange={(v) => update('precision', v as RCSettingsType['precision'])}
          className="flex flex-row gap-4"
        >
          {PRECISION_OPTIONS.map(({ value, label }) => (
            <div key={value} className="flex items-center gap-1.5">
              <RadioGroupItem value={value} id={`precision-${value}`} />
              <Label htmlFor={`precision-${value}`} className="text-slate-400 cursor-pointer">
                {label}
              </Label>
            </div>
          ))}
        </RadioGroup>
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

      {/* Component filter */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label>Keep largest component only</Label>
          <p className="text-xs text-slate-500">Filters disconnected components</p>
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

      {/* DEV stub section */}
      <StubToggle
        tool="RealityCapture"
        enabled={settings.stub_enabled}
        onChange={handleStubChange}
        durationSeconds={settings.stub_duration}
        onDurationChange={handleStubDurationChange}
      />
    </div>
  );
};

export default RCSettings;
