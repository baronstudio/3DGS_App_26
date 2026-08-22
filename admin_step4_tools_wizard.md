# AGENT PROMPT — Admin UI Step 4/4: Tools Registry & Wizard Step Customizer
## For: GitHub Copilot Agent / Claude Code / VS Code
## Requires: Steps 1, 2 and 3 completed and working

---

## MISSION

Implement the last two sections of the Admin UI:
- **Tools section**: register new external tools, set exe paths, configure their CLI
- **Wizard Steps section**: toggle, reorder, and rename wizard steps

---

## STEP 4 SCOPE — DO ONLY THIS

- [ ] Tools registry: list + add + edit + delete custom tools
- [ ] Tool path validator (checks exe exists on disk)
- [ ] Wizard step customizer: toggle on/off, drag to reorder, rename
- [ ] Backend endpoints for tools registry and wizard config
- [ ] Persist everything in `config.json`

---

## PART A — TOOLS REGISTRY

### Data model in `config.json`

```json
{
  "tools_registry": [
    {
      "id": "ffmpeg",
      "name": "FFmpeg",
      "builtin": true,
      "exe_path": "ffmpeg",
      "description": "Video frame extraction",
      "help_url": "https://ffmpeg.org/ffmpeg.html",
      "flags_file": "backend/admin/flags/ffmpeg_flags.json",
      "wizard_step": 2
    },
    {
      "id": "rc",
      "name": "RealityCapture",
      "builtin": true,
      "exe_path": "C:/Program Files/Epic Games/RealityScan/RealityScan.exe",
      "description": "Camera alignment via photogrammetry",
      "help_url": "https://rshelp.capturingreality.com/en-US/appbasics/allcommands.htm",
      "flags_file": "backend/admin/flags/rc_flags.json",
      "wizard_step": 3
    },
    {
      "id": "lfs",
      "name": "LichtFeld Studio",
      "builtin": true,
      "exe_path": null,
      "description": "3DGS training",
      "help_url": "https://github.com/MrNeRF/LichtFeld-Studio/wiki",
      "flags_file": "backend/admin/flags/lfs_flags.json",
      "wizard_step": 4
    }
  ]
}
```

Custom tools added by the user follow the same schema with `"builtin": false`.

### Backend endpoints

```python
GET    /api/admin/tools                    # List all tools in registry
POST   /api/admin/tools                    # Add new custom tool
PUT    /api/admin/tools/{tool_id}          # Update tool config
DELETE /api/admin/tools/{tool_id}          # Delete (builtin=false only)
POST   /api/admin/tools/{tool_id}/validate # Check exe path exists + responds
```

### Validate endpoint

```python
@router.post("/api/admin/tools/{tool_id}/validate")
async def validate_tool(tool_id: str):
    tool = get_tool_by_id(tool_id)
    exe = Path(tool["exe_path"]) if tool["exe_path"] else None

    if not exe:
        return {"status": "not_configured", "message": "No exe path set"}

    if not exe.exists():
        return {"status": "not_found", "message": f"File not found: {exe}"}

    # Try running with --help or --version
    try:
        proc = await asyncio.create_subprocess_exec(
            str(exe), "--help",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=5.0)
        return {"status": "ok", "message": "Tool responds correctly"}
    except asyncio.TimeoutError:
        return {"status": "timeout", "message": "Tool did not respond in 5s"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

### Frontend — Tools section layout

```
┌─────────────────────────────────────────────────────┐
│  Tools Registry                    [+ Add tool]     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │  🎞️  FFmpeg               builtin  ● OK     │   │
│  │  Path: ffmpeg (in PATH)            [Edit]   │   │
│  └──────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────┐   │
│  │  📷  RealityCapture        builtin  ● OK     │   │
│  │  Path: C:/Program Files/...         [Edit]   │   │
│  └──────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────┐   │
│  │  ✨  LichtFeld Studio      builtin  ❌ Not set│   │
│  │  Path: not configured               [Edit]   │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  ── Custom tools ──────────────────────────────     │
│  (none yet)                                         │
└─────────────────────────────────────────────────────┘
```

### Add / Edit tool modal

Triggered by `[+ Add tool]` or `[Edit]`:

```html
<div class="modal" x-show="toolModalOpen">
  <div class="modal-card">
    <h3 x-text="editingTool ? 'Edit Tool' : 'Add New Tool'"></h3>

    <label>Tool name</label>
    <input type="text" x-model="toolForm.name" placeholder="e.g. Blender" />

    <label>Executable path</label>
    <div class="path-row">
      <input type="text" x-model="toolForm.exe_path"
        placeholder="C:/path/to/tool.exe or just 'toolname' if in PATH" />
      <button @click="validateToolPath()" class="btn-validate">
        <span x-text="validating ? '...' : 'Check'"></span>
      </button>
    </div>
    <div class="validate-result"
      x-show="validateResult"
      :class="validateResult?.status === 'ok' ? 'result-ok' : 'result-error'"
      x-text="validateResult?.message">
    </div>

    <label>Description</label>
    <input type="text" x-model="toolForm.description"
      placeholder="What does this tool do?" />

    <label>Help / docs URL (optional)</label>
    <input type="url" x-model="toolForm.help_url"
      placeholder="https://..." />

    <label>Assign to wizard step (optional)</label>
    <select x-model.number="toolForm.wizard_step">
      <option value="">No step (config only)</option>
      <template x-for="step in wizardSteps" :key="step.id">
        <option :value="step.order" x-text="step.order + ' — ' + step.label"></option>
      </template>
      <option value="99">New step at the end</option>
    </select>

    <div class="modal-footer">
      <button class="btn-secondary" @click="toolModalOpen = false">Cancel</button>
      <button class="btn-primary" @click="saveTool()">
        <span x-text="editingTool ? 'Save changes' : 'Add tool'"></span>
      </button>
    </div>
  </div>
</div>
```

---

## PART B — WIZARD STEP CUSTOMIZER

### Data model in `config.json`

```json
{
  "wizard_steps": [
    { "id": "import",   "order": 1, "label": "Import",        "enabled": true,  "locked": true  },
    { "id": "extract",  "order": 2, "label": "Extract Frames", "enabled": true,  "locked": false },
    { "id": "rc",       "order": 3, "label": "RC Alignment",   "enabled": true,  "locked": false },
    { "id": "lfs",      "order": 4, "label": "LFS Training",   "enabled": true,  "locked": false },
    { "id": "export",   "order": 5, "label": "Export",         "enabled": true,  "locked": false },
    { "id": "blender",  "order": 6, "label": "Blender Scene",  "enabled": true,  "locked": false }
  ]
}
```

`locked: true` = step cannot be disabled or reordered (Import is always first).

### Backend endpoints

```python
GET  /api/admin/wizard/steps          # Returns current wizard steps config
PUT  /api/admin/wizard/steps          # Save full steps array (order + enabled + labels)
```

### Frontend — Wizard Steps section layout

```
┌─────────────────────────────────────────────────────┐
│  Wizard Steps                                       │
│  Drag to reorder. Toggle to enable/disable.         │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ⠿  1  Import          [locked]     ● enabled      │
│  ⠿  2  Extract Frames  [rename]     ● enabled  ◉   │
│  ⠿  3  RC Alignment    [rename]     ● enabled  ◉   │
│  ⠿  4  LFS Training    [rename]     ● enabled  ◉   │
│  ⠿  5  Export          [rename]     ● enabled  ◉   │
│  ⠿  6  Blender Scene   [rename]     ○ disabled ◉   │
│                                                     │
│  ⚠️  Disabled steps are skipped in the wizard.     │
│  Reordering takes effect on the next new project.  │
│                                                     │
│  [Reset to default order]          [Save changes]  │
└─────────────────────────────────────────────────────┘
```

`⠿` = drag handle (visual only in this implementation — see drag note below).

### Drag to reorder — implementation note

Use the **HTML5 Drag and Drop API** (no external library needed):

```javascript
// In adminApp data:
wizardSteps: [],
dragSrcIndex: null,

async loadWizardSteps() {
  const r = await fetch('/api/admin/wizard/steps')
  this.wizardSteps = await r.json()
},

onDragStart(index) {
  this.dragSrcIndex = index
},

onDragOver(e, index) {
  e.preventDefault()
  if (this.dragSrcIndex === index) return
  const steps = [...this.wizardSteps]
  const [moved] = steps.splice(this.dragSrcIndex, 1)
  steps.splice(index, 0, moved)
  // Update order numbers
  steps.forEach((s, i) => s.order = i + 1)
  this.wizardSteps = steps
  this.dragSrcIndex = index
},

onDragEnd() {
  this.dragSrcIndex = null
},

async saveWizardSteps() {
  await fetch('/api/admin/wizard/steps', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(this.wizardSteps)
  })
  this.stepsSaved = true
  setTimeout(() => { this.stepsSaved = false }, 2000)
}
```

### Step row HTML

```html
<template x-for="(step, index) in wizardSteps" :key="step.id">
  <div class="step-row-drag"
    :class="{ 'dragging': dragSrcIndex === index, 'locked': step.locked }"
    draggable="true"
    @dragstart="onDragStart(index)"
    @dragover="onDragOver($event, index)"
    @dragend="onDragEnd()">

    <!-- Drag handle -->
    <span class="drag-handle" x-show="!step.locked">⠿</span>
    <span class="drag-handle locked-icon" x-show="step.locked">🔒</span>

    <!-- Step order badge -->
    <span class="step-order" x-text="step.order"></span>

    <!-- Label (editable inline for non-locked steps) -->
    <span x-show="step.locked" class="step-label" x-text="step.label"></span>
    <input x-show="!step.locked"
      type="text"
      x-model="step.label"
      class="step-label-input"
      maxlength="32" />

    <!-- Enable/disable toggle -->
    <label class="toggle" x-show="!step.locked">
      <input type="checkbox"
        :checked="step.enabled"
        @change="step.enabled = $event.target.checked" />
      <span class="slider"></span>
    </label>
    <span x-show="step.locked" class="locked-label">always on</span>
  </div>
</template>
```

---

## IMPORTANT CONSTRAINTS FOR THE AGENT

1. **Builtin tools cannot be deleted.** The delete button must not appear for tools where `builtin: true`. Show a lock icon instead.

2. **Step order changes are non-destructive.** The wizard reads step order from `config.json` at runtime. Existing projects are not affected by reordering — they store their own step state by step ID, not by order number.

3. **Disabled steps in the wizard** — when a step is disabled in `config.json`, the `pipeline_runner.py` must skip it. Update `pipeline_runner.py` to read `wizard_steps` from config and skip steps where `enabled: false`.

4. **Custom tool CLI config** — when a user adds a custom tool, they cannot use the flag autocomplete system (no flags JSON file). Show a plain textarea for the command template instead, with placeholder: `{exe} -input {input_path} -output {output_path}`. Document the available template variables.

5. **No drag-and-drop library** — use native HTML5 DnD only. Keep it simple.

---

## ACCEPTANCE CRITERIA

After this step:
- Tools list shows all 3 builtin tools with their status (OK / Not configured)
- "Check" button validates the exe path and shows result inline
- Add Tool modal saves a new tool to `config.json`
- Builtin tools show edit (exe path only) but no delete button
- Wizard steps can be toggled on/off and labels can be renamed
- Drag reordering works (steps snap to new positions)
- Save persists to `config.json`, page reload shows saved state
- `pipeline_runner.py` skips disabled steps
- Admin UI at `http://127.0.0.1:8000/` is fully functional across all 4 sections
