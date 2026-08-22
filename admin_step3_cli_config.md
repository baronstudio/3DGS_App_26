# AGENT PROMPT — Admin UI Step 3/4: CLI Configuration Editor
## For: GitHub Copilot Agent / Claude Code / VS Code
## Requires: Steps 1 and 2 completed and working

---

## MISSION

Implement the **CLI Config section** of the Admin UI.
A visual editor for the command-line flags of each tool in the pipeline.
Includes autocomplete from known flag lists, and live command preview.

---

## STEP 3 SCOPE — DO ONLY THIS

- [ ] Flag database (JSON) for each tool
- [ ] Per-tool CLI editor with flag toggles and autocomplete
- [ ] Live command preview (reconstructs the full CLI string)
- [ ] Save/load configurations per tool
- [ ] Backend endpoints to persist CLI configs

---

## FLAG DATABASE — `backend/admin/flags/`

Create one JSON file per tool with the known flags.
These are static files — no scraping needed, flags are hardcoded from official docs.

### `backend/admin/flags/ffmpeg_flags.json`

```json
{
  "tool": "FFmpeg",
  "help_url": "https://ffmpeg.org/ffmpeg.html",
  "flags": [
    {
      "flag": "-vf",
      "type": "string",
      "default": "fps=2,mpdecimate",
      "description": "Video filter chain. fps=N sets extraction rate. mpdecimate removes duplicate frames.",
      "example": "fps=2,mpdecimate",
      "category": "video"
    },
    {
      "flag": "-qscale:v",
      "type": "integer",
      "default": 2,
      "min": 1,
      "max": 31,
      "description": "JPEG quality for extracted frames. 1=best quality, 31=worst. Recommended: 1-5.",
      "category": "quality"
    },
    {
      "flag": "-ss",
      "type": "string",
      "default": null,
      "description": "Start time offset. Format: HH:MM:SS or seconds. Skips the beginning of the video.",
      "example": "00:00:05",
      "category": "trim"
    },
    {
      "flag": "-to",
      "type": "string",
      "default": null,
      "description": "Stop time. Format: HH:MM:SS or seconds.",
      "example": "00:02:00",
      "category": "trim"
    },
    {
      "flag": "-frames:v",
      "type": "integer",
      "default": null,
      "description": "Maximum number of frames to extract. Stops extraction after N frames.",
      "category": "limit"
    }
  ]
}
```

### `backend/admin/flags/rc_flags.json`

```json
{
  "tool": "RealityScan",
  "help_url": "https://rshelp.capturingreality.com/en-US/appbasics/allcommands.htm",
  "flags": [
    {
      "flag": "-align",
      "type": "boolean",
      "default": true,
      "description": "Align all images. Detects features, matches them, and runs bundle adjustment.",
      "category": "core"
    },
    {
      "flag": "-selectMaximalComponent",
      "type": "boolean",
      "default": true,
      "description": "Keep only the largest connected component. Removes stray unaligned cameras.",
      "category": "core"
    },
    {
      "flag": "-setAlignmentPreset",
      "type": "enum",
      "default": "Normal",
      "options": ["Preview", "Normal", "High"],
      "description": "Alignment quality preset. High = slower but more accurate.",
      "category": "quality"
    },
    {
      "flag": "-exportRegistration",
      "type": "string",
      "default": "rc_output/registration.csv",
      "description": "Export camera registration (positions + orientations) as CSV.",
      "category": "export"
    },
    {
      "flag": "-exportSparsePointCloud",
      "type": "string",
      "default": "rc_output/pointcloud.ply",
      "description": "Export sparse point cloud as PLY file for LichtFeld Studio import.",
      "category": "export"
    },
    {
      "flag": "-quit",
      "type": "boolean",
      "default": true,
      "description": "Quit RealityScan after all commands complete. Required for automation.",
      "category": "core"
    }
  ]
}
```

### `backend/admin/flags/lfs_flags.json`

```json
{
  "tool": "LichtFeld Studio",
  "help_url": "https://github.com/MrNeRF/LichtFeld-Studio/wiki",
  "flags": [
    {
      "flag": "-d",
      "type": "string",
      "default": "rc_output/",
      "description": "Path to COLMAP dataset directory (must contain sparse/0/ subfolder).",
      "category": "core",
      "required": true
    },
    {
      "flag": "-o",
      "type": "string",
      "default": "lfs_output/",
      "description": "Output directory for trained Gaussian Splat files.",
      "category": "core",
      "required": true
    },
    {
      "flag": "-i",
      "type": "integer",
      "default": 30000,
      "min": 1000,
      "max": 100000,
      "description": "Number of training iterations. More = better quality, longer training time.",
      "category": "training"
    },
    {
      "flag": "--strategy",
      "type": "enum",
      "default": "default",
      "options": ["default", "mcmc"],
      "description": "Densification strategy. MCMC is more stable for large scenes.",
      "category": "training"
    },
    {
      "flag": "--eval",
      "type": "boolean",
      "default": true,
      "description": "Run evaluation after training. Computes PSNR, SSIM, LPIPS metrics.",
      "category": "eval"
    },
    {
      "flag": "--save-eval-images",
      "type": "boolean",
      "default": false,
      "description": "Save rendered evaluation images to output directory.",
      "category": "eval"
    },
    {
      "flag": "--render-mode",
      "type": "enum",
      "default": "RGB",
      "options": ["RGB", "RGB_D", "DEPTH"],
      "description": "Render mode for output visualization. RGB_D includes depth channel.",
      "category": "output"
    },
    {
      "flag": "--headless",
      "type": "boolean",
      "default": true,
      "description": "Run without GUI. Required for pipeline automation.",
      "category": "core"
    }
  ]
}
```

---

## BACKEND — CLI config endpoints

Add to `backend/api/routes/settings.py`:

```python
GET  /api/admin/cli/flags/{tool}       # Returns flag definitions JSON for a tool
GET  /api/admin/cli/config/{tool}      # Returns current saved CLI config for a tool
PUT  /api/admin/cli/config/{tool}      # Save CLI config for a tool
POST /api/admin/cli/preview/{tool}     # Returns reconstructed CLI command string
```

### Tools identifiers: `ffmpeg` | `rc` | `lfs`

### CLI config storage

Saved in `config.json` under a `cli_configs` key:

```json
{
  "cli_configs": {
    "ffmpeg": {
      "-vf": "fps=2,mpdecimate",
      "-qscale:v": 2
    },
    "rc": {
      "-align": true,
      "-selectMaximalComponent": true,
      "-setAlignmentPreset": "Normal",
      "-quit": true
    },
    "lfs": {
      "-i": 30000,
      "--strategy": "default",
      "--eval": true,
      "--headless": true
    }
  }
}
```

### Preview endpoint logic

```python
@router.post("/api/admin/cli/preview/{tool}")
async def preview_cli(tool: str, config: dict):
    """Reconstructs the full CLI command string from a config dict."""
    exe_map = {
        "ffmpeg": app_config.tools.ffmpeg_path or "ffmpeg",
        "rc": app_config.tools.rc_exe_path or "RealityScan.exe",
        "lfs": app_config.tools.lfs_exe_path or "LichtFeld-Studio.exe",
    }
    parts = [exe_map[tool]]
    for flag, value in config.items():
        if value is True:
            parts.append(flag)
        elif value is False or value is None:
            continue
        else:
            parts.extend([flag, str(value)])
    return {"command": " ".join(parts)}
```

---

## FRONTEND — CLI Config section

### Layout

```
┌─────────────────────────────────────────────────┐
│  CLI Configuration                              │
│  [FFmpeg]  [RealityScan]  [LichtFeld Studio] │  ← tool tabs
├─────────────────────────────────────────────────┤
│                                                 │
│  📖 Docs: https://...            [Open ↗]       │
│                                                 │
│  ┌─ video ─────────────────────────────────┐   │
│  │  -vf      [fps=2,mpdecimate      ] [?]  │   │
│  │  -qscale  [2                     ] [?]  │   │
│  └─────────────────────────────────────────┘   │
│  ┌─ trim ──────────────────────────────────┐   │
│  │  -ss      [          ] (optional)  [?]  │   │
│  │  -to      [          ] (optional)  [?]  │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  ┌─ Command Preview ───────────────────────┐   │
│  │  ffmpeg -vf "fps=2,mpdecimate"          │   │
│  │    -qscale:v 2 frames/frame_%04d.jpg    │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  [Reset to defaults]           [Save config]    │
└─────────────────────────────────────────────────┘
```

### Alpine.js data additions

```javascript
// Add to adminApp:
activeTool: 'ffmpeg',   // 'ffmpeg' | 'rc' | 'lfs'
toolFlags: {},          // flag definitions loaded from /api/admin/cli/flags/{tool}
toolConfig: {},         // current values loaded from /api/admin/cli/config/{tool}
cliPreview: '',         // reconstructed command string
configSaved: false,     // flash confirmation

tools: [
  { id: 'ffmpeg', label: 'FFmpeg',            icon: '🎞️' },
  { id: 'rc',     label: 'RealityScan',    icon: '📷' },
  { id: 'lfs',    label: 'LichtFeld Studio',  icon: '✨' },
],

async loadToolConfig(toolId) {
  this.activeTool = toolId
  this.cliPreview = ''
  const [flagsRes, configRes] = await Promise.all([
    fetch(`/api/admin/cli/flags/${toolId}`),
    fetch(`/api/admin/cli/config/${toolId}`)
  ])
  this.toolFlags = await flagsRes.json()
  this.toolConfig = await configRes.json()
  await this.refreshPreview()
},

async refreshPreview() {
  const r = await fetch(`/api/admin/cli/preview/${this.activeTool}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(this.toolConfig)
  })
  const data = await r.json()
  this.cliPreview = data.command
},

async saveToolConfig() {
  await fetch(`/api/admin/cli/config/${this.activeTool}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(this.toolConfig)
  })
  this.configSaved = true
  setTimeout(() => { this.configSaved = false }, 2000)
},

async resetToolConfig() {
  // Reloads defaults from flag definitions
  const defaults = {}
  for (const flag of this.toolFlags.flags) {
    if (flag.default !== null) defaults[flag.flag] = flag.default
  }
  this.toolConfig = defaults
  await this.refreshPreview()
}
```

### Flag row rendering

Render a different input type per flag type:

```html
<template x-for="flag in toolFlags.flags" :key="flag.flag">
  <div class="flag-row">
    <div class="flag-header">
      <code class="flag-name" x-text="flag.flag"></code>
      <span class="flag-badge" x-text="flag.category"></span>
      <!-- Tooltip trigger -->
      <span class="flag-help" :title="flag.description + (flag.example ? '\nExample: ' + flag.example : '')">?</span>
    </div>

    <!-- boolean flag → toggle switch -->
    <div x-show="flag.type === 'boolean'">
      <label class="toggle">
        <input type="checkbox"
          :checked="toolConfig[flag.flag]"
          @change="toolConfig[flag.flag] = $event.target.checked; refreshPreview()" />
        <span class="slider"></span>
      </label>
    </div>

    <!-- enum flag → select dropdown -->
    <div x-show="flag.type === 'enum'">
      <select class="flag-select"
        x-model="toolConfig[flag.flag]"
        @change="refreshPreview()">
        <template x-for="opt in flag.options" :key="opt">
          <option :value="opt" x-text="opt"></option>
        </template>
      </select>
    </div>

    <!-- integer flag → number input + range slider -->
    <div x-show="flag.type === 'integer'" class="flag-number">
      <input type="number"
        :min="flag.min" :max="flag.max"
        x-model.number="toolConfig[flag.flag]"
        @change="refreshPreview()"
        class="flag-input" />
      <input x-show="flag.min && flag.max"
        type="range"
        :min="flag.min" :max="flag.max"
        x-model.number="toolConfig[flag.flag]"
        @input="refreshPreview()"
        class="flag-range" />
    </div>

    <!-- string flag → text input -->
    <div x-show="flag.type === 'string'">
      <input type="text"
        x-model="toolConfig[flag.flag]"
        @input="refreshPreview()"
        :placeholder="flag.example || flag.default || ''"
        class="flag-input-text" />
      <span x-show="!flag.required" class="optional-label">optional</span>
    </div>
  </div>
</template>
```

### Command preview box

```html
<div class="preview-box">
  <div class="preview-header">
    <span>Command Preview</span>
    <button @click="navigator.clipboard.writeText(cliPreview)" title="Copy">⎘ Copy</button>
  </div>
  <pre class="preview-code" x-text="cliPreview || 'Configure flags above...'"></pre>
</div>
```

---

## ACCEPTANCE CRITERIA

After this step:
- Three tool tabs switch correctly
- Each flag renders the correct input type (checkbox / select / number+slider / text)
- Changing any value updates the Command Preview in real time
- Save persists to `config.json` (verified by page reload)
- Reset restores default values from the flag JSON
- Docs link opens the official help URL in a new tab
- The pipeline `step_rc.py` and `step_lfs.py` read their CLI config
  from `config.json` cli_configs on each run (not hardcoded)
