## CONTEXT
Project: 3DGS Pipeline Web App — React + TypeScript
After Sessions 5-8: full app implemented, needs settings UI.
Current state: FFmpegSettings, RCSettings, LFSSettings → all return <div>...</div>
SettingsDrawer.tsx → unknown state

## TASK: Implement all settings components

### 1. components/settings/SettingsDrawer.tsx
Wrapper using shadcn Sheet component:
- Props: open: boolean, onClose: () => void, title: string, children: ReactNode
- Uses <Sheet> side="right" with close button
- Width: 400px (sm:w-[400px])
- Sections separated by <Separator>
- "Reset to defaults" button at bottom (prop: onReset?: () => void)

### 2. components/settings/FFmpegSettings.tsx
Props: settings: FFmpegSettingsType, onChange: (s: FFmpegSettingsType) => void

Controls:
  FPS: RadioGroup options [0.5, 1, 2, 3, 5] — default 2
  mpdecimate: Switch (on/off) — default on
    Info tooltip: "Removes duplicate frames — recommended"
  JPEG quality: Slider 1–5 step 1 — default 2
    Label: "Quality (lower = better)"
  Max frames: NumberInput or Slider 0–500 (0=unlimited) — default 0
    Label shows "Unlimited" when 0

FFmpegSettingsType: { fps: number, mpdecimate: boolean, quality: number, max_frames: number }

### 3. components/settings/RCSettings.tsx
Props: settings: RCSettingsType, onChange: (s: RCSettingsType) => void

Controls:
  Alignment precision: RadioGroup [Preview, Normal, High] — default Normal
  Max features per image: Slider 40000–80000 step 1000
    Display: formatted number
  Component filter: Switch "Keep largest component only" — default on
  Custom .rsbox file: file input (optional)
  
  ── DEV section (orange border) ──
  <StubToggle tool="RealityScan" enabled={settings.stub_enabled} onChange={...}
    durationSeconds={settings.stub_duration} onDurationChange={...} />

On any change: call PUT /api/settings/ with updated stubs config via useSettings().updateSettings

RCSettingsType: { precision: "Preview"|"Normal"|"High", max_features: number, keep_largest: boolean, stub_enabled: boolean, stub_duration: number }

### 4. components/settings/LFSSettings.tsx
Props: settings: LFSSettingsType, onChange: (s: LFSSettingsType) => void

Controls:
  Iterations: Slider 5000–100000 step 1000 — default 30000
    Value display: formatted (30,000)
  Strategy: RadioGroup [Default, MCMC] — default Default
    MCMC info: "Markov Chain Monte Carlo — better quality, slower"
  Learning rate: NumberInput float 0.0001–0.01 step 0.0001 — default 0.001
  Save interval: NumberInput 0–10000 (0=disabled) — default 0
  Render mode: Select [RGB, RGB_D, DEPTH] — default RGB
  Eval mode: Switch — default false
  Save eval images: Switch (only enabled if eval=true) — default false
  Background color: color picker (hex) — default #000000

  ── DEV section ──
  <StubToggle tool="LichtFeld Studio" enabled={...} onChange={...}
    durationSeconds={...} onDurationChange={...} />

LFSSettingsType: { iterations: number, strategy: "default"|"mcmc", lr: number, save_interval: number, render_mode: string, eval: boolean, save_eval_images: boolean, background_color: string, stub_enabled: boolean, stub_duration: number }

## CONSTRAINTS
- All shadcn components: Switch, Slider, RadioGroup, Select, Input, Label
- No local state for settings values — receive via props, propagate via onChange
- StubToggle onChange must trigger PUT /api/settings/ immediately (not waiting for form submit)
- Show current value next to every Slider (inline, cyan color)
- TypeScript interfaces for all settings types in src/types/index.ts