# AGENT PROMPT — Admin UI Step 2/4: Project Management
## For: GitHub Copilot Agent / Claude Code / VS Code
## Requires: Step 1 completed and working

---

## MISSION

Implement the **Projects section** of the Admin UI.
Replace the Step 2 placeholder with a functional project management panel.

---

## STEP 2 SCOPE — DO ONLY THIS

- [ ] Project grid with card previews
- [ ] Per-project actions: Delete, Copy, Edit step status
- [ ] Project detail drawer (slide-in panel)
- [ ] Backend API endpoints for project management
- [ ] Empty state when no projects exist

---

## BACKEND — new endpoints in `backend/api/routes/projects.py`

Add these endpoints (they may partially exist — extend, do not duplicate):

```python
GET    /api/admin/projects              # List all projects with metadata
GET    /api/admin/projects/{id}         # Single project full detail
DELETE /api/admin/projects/{id}         # Delete project + files on disk
POST   /api/admin/projects/{id}/copy    # Duplicate project folder + DB record
PATCH  /api/admin/projects/{id}/steps   # Edit step completion status
```

### Project list response shape

```json
[
  {
    "id": "proj_abc123",
    "name": "Garden scan 01",
    "created_at": "2026-05-17T14:23:00",
    "updated_at": "2026-05-17T17:26:10",
    "status": "training",
    "current_step": 4,
    "total_steps": 6,
    "steps": {
      "1_import":   "done",
      "2_extract":  "done",
      "3_rc":       "done",
      "4_lfs":      "running",
      "5_export":   "pending",
      "6_blender":  "pending"
    },
    "frame_count": 185,
    "has_ply": false,
    "has_splat": false,
    "has_blend": false,
    "input_video": "DJI_0042.MP4",
    "disk_usage_mb": 342,
    "thumbnail_url": null
  }
]
```

Step status values: `"pending"` | `"running"` | `"done"` | `"error"` | `"skipped"`

### Copy endpoint logic

```python
@router.post("/api/admin/projects/{id}/copy")
async def copy_project(id: str):
    # 1. Load original project from DB
    # 2. Create new project record with name = "{original_name} (copy)"
    # 3. Copy projects/{id}/ folder to projects/{new_id}/
    # 4. Reset all step statuses to "pending" in the copy
    # 5. Return new project record
```

### Edit step status endpoint

```python
@router.patch("/api/admin/projects/{id}/steps")
async def edit_steps(id: str, body: dict):
    # body: {"3_rc": "done", "4_lfs": "pending"}
    # Validates step keys and status values before writing
    # Use case: manually mark a step as done to skip it on next run
```

---

## FRONTEND — Projects section in `backend/admin/index.html`

Replace the Projects placeholder with this Alpine.js component.

### Data model addition

```javascript
// Add to adminApp data:
projects: [],
projectsLoading: false,
selectedProject: null,
drawerOpen: false,
deleteConfirm: null,   // project id pending delete confirmation

async loadProjects() {
  this.projectsLoading = true
  try {
    const r = await fetch('/api/admin/projects')
    this.projects = await r.json()
  } finally {
    this.projectsLoading = false
  }
},

async deleteProject(id) {
  if (this.deleteConfirm !== id) {
    this.deleteConfirm = id
    setTimeout(() => { this.deleteConfirm = null }, 3000)
    return
  }
  await fetch(`/api/admin/projects/${id}`, { method: 'DELETE' })
  this.deleteConfirm = null
  await this.loadProjects()
},

async copyProject(id) {
  await fetch(`/api/admin/projects/${id}/copy`, { method: 'POST' })
  await this.loadProjects()
},

openDrawer(project) {
  this.selectedProject = { ...project }
  this.drawerOpen = true
},

async saveStepStatus() {
  await fetch(`/api/admin/projects/${this.selectedProject.id}/steps`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(this.selectedProject.steps)
  })
  this.drawerOpen = false
  await this.loadProjects()
}
```

### Project grid layout

```
┌──────────────────────────────────────────────────┐
│  Projects  [3]                    [↻ Refresh]    │
├──────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ [thumb]  │  │ [thumb]  │  │ [thumb]  │       │
│  │          │  │          │  │          │       │
│  │Garden 01 │  │Street 02 │  │Test scan │       │
│  │Step 4/6  │  │Done ✅   │  │Error ❌  │       │
│  │342 MB    │  │128 MB    │  │12 MB     │       │
│  │[Edit][✕] │  │[Edit][✕] │  │[Edit][✕] │       │
│  └──────────┘  └──────────┘  └──────────┘       │
└──────────────────────────────────────────────────┘
```

### Card HTML structure

```html
<div class="project-card" @click="openDrawer(project)">
  <!-- Thumbnail or fallback icon -->
  <div class="thumb">
    <img x-show="project.thumbnail_url" :src="project.thumbnail_url" />
    <div x-show="!project.thumbnail_url" class="thumb-fallback">🌐</div>
  </div>

  <!-- Info -->
  <div class="card-info">
    <p class="card-name" x-text="project.name"></p>
    <p class="card-step">
      Step <span x-text="project.current_step"></span>/6
      — <span x-text="project.status"></span>
    </p>
    <p class="card-meta">
      <span x-text="project.frame_count"></span> frames
      · <span x-text="project.disk_usage_mb"></span> MB
    </p>
  </div>

  <!-- Step progress pills -->
  <div class="step-pills">
    <template x-for="(status, key) in project.steps" :key="key">
      <span class="pill"
        :class="{
          'pill-done':    status === 'done',
          'pill-running': status === 'running',
          'pill-error':   status === 'error',
          'pill-pending': status === 'pending'
        }"
        :title="key">
      </span>
    </template>
  </div>

  <!-- Actions — stop propagation to avoid opening drawer -->
  <div class="card-actions" @click.stop>
    <button class="btn-icon" @click="copyProject(project.id)" title="Copy">⎘</button>
    <button class="btn-icon btn-danger"
      :class="{ 'confirming': deleteConfirm === project.id }"
      @click="deleteProject(project.id)"
      :title="deleteConfirm === project.id ? 'Click again to confirm' : 'Delete'">
      <span x-text="deleteConfirm === project.id ? '⚠️ Confirm' : '✕'"></span>
    </button>
  </div>
</div>
```

### Step status drawer

Slides in from right when a card is clicked.

```html
<div class="drawer" :class="{ 'drawer-open': drawerOpen }">
  <div class="drawer-header">
    <h3 x-text="selectedProject?.name"></h3>
    <button @click="drawerOpen = false">✕</button>
  </div>

  <div class="drawer-body" x-show="selectedProject">
    <!-- Project metadata -->
    <div class="meta-row">
      <span class="label">Input video</span>
      <span x-text="selectedProject?.input_video"></span>
    </div>
    <div class="meta-row">
      <span class="label">Frames</span>
      <span x-text="selectedProject?.frame_count"></span>
    </div>
    <div class="meta-row">
      <span class="label">Disk usage</span>
      <span x-text="selectedProject?.disk_usage_mb + ' MB'"></span>
    </div>
    <div class="meta-row">
      <span class="label">Has PLY</span>
      <span x-text="selectedProject?.has_ply ? '✅' : '—'"></span>
    </div>

    <!-- Step status editor -->
    <h4>Step Status</h4>
    <p class="hint">Edit manually to skip or re-run specific steps.</p>
    <template x-for="(status, key) in selectedProject?.steps" :key="key">
      <div class="step-row">
        <span class="step-label" x-text="key.replace('_', ' ')"></span>
        <select x-model="selectedProject.steps[key]" class="step-select">
          <option value="pending">Pending</option>
          <option value="done">Done</option>
          <option value="error">Error</option>
          <option value="skipped">Skipped</option>
        </select>
      </div>
    </template>

    <button class="btn-primary" @click="saveStepStatus()">Save changes</button>
  </div>
</div>
```

### Empty state

```html
<div x-show="!projectsLoading && projects.length === 0" class="empty-state">
  <p>🌐</p>
  <p>No projects yet.</p>
  <p class="hint">Start a new pipeline from the
    <a href="http://localhost:5173" target="_blank">Wizard UI</a>.
  </p>
</div>
```

---

## ACCEPTANCE CRITERIA

After this step:
- Projects grid loads from the real SQLite database
- Clicking a card opens the drawer with project details
- Step status dropdowns can be changed and saved
- Delete requires double-click confirmation (3s timeout)
- Copy creates a duplicate project visible in the grid
- Empty state shown when no projects exist
- Wizard UI at port 5173 is unaffected
