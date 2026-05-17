# AGENT PROMPT — Admin UI Step 1/4: Foundation & Shell
## For: GitHub Copilot Agent / Claude Code / VS Code

---

## MISSION

Replace the current "Hello World" page at `http://127.0.0.1:8000/`
with a proper **Admin UI shell** served directly by FastAPI as a single static HTML file.

No new npm project. No new Vite instance. No new port.
One HTML file, Alpine.js from CDN, served by FastAPI.

---

## STEP 1 SCOPE — DO ONLY THIS

- [ ] Create the HTML shell file with navigation
- [ ] Mount it in FastAPI to replace Hello World
- [ ] Implement the 4 nav sections as empty placeholder panels
- [ ] Add a status bar showing backend health

**Do NOT implement section content yet — placeholders only.**

---

## FILE TO CREATE

`backend/admin/index.html`

---

## FASTAPI MOUNT — update `backend/main.py`

Replace the current Hello World route with static file serving:

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

app = FastAPI()

ADMIN_DIR = Path(__file__).parent / "admin"

# Serve admin UI at root
@app.get("/")
async def admin_root():
    return FileResponse(ADMIN_DIR / "index.html")

# Serve any static asset in admin/ (css, js, icons if added later)
app.mount("/admin-static", StaticFiles(directory=str(ADMIN_DIR)), name="admin-static")
```

Add `aiofiles` to `requirements.txt` if not already present (needed by StaticFiles).

---

## HTML FILE SPECIFICATION

Single file: `backend/admin/index.html`
All CSS inline in `<style>`. All JS inline in `<script>`.
Alpine.js loaded from CDN: `https://cdnjs.cloudflare.com/ajax/libs/alpinejs/3.13.5/cdn.min.js`

### Visual style
- Dark theme — background `#0f1117`, sidebar `#161b22`
- Accent color: electric cyan `#00D4FF`
- Font: system monospace for values, sans-serif for labels
- Compact and utilitarian — this is a dev/admin tool, not a marketing page

### Layout

```
┌─────────────────────────────────────────────────────┐
│  🎛️  3DGS Pipeline — Admin                    v1.0  │  ← top bar
├──────────────┬──────────────────────────────────────┤
│              │                                      │
│  Projects    │                                      │
│  CLI Config  │         [Section Content]            │
│  Tools       │                                      │
│  Wizard      │                                      │
│              │                                      │
├──────────────┴──────────────────────────────────────┤
│  Backend: ● Online  |  Port 8000  |  Wizard: 5173  │  ← status bar
└─────────────────────────────────────────────────────┘
```

### Alpine.js data model

```javascript
Alpine.data('adminApp', () => ({
  activeSection: 'projects',  // 'projects' | 'cli' | 'tools' | 'wizard'
  backendStatus: 'checking',  // 'online' | 'offline' | 'checking'

  sections: [
    { id: 'projects', label: 'Projects',    icon: '📁' },
    { id: 'cli',      label: 'CLI Config',  icon: '⚙️'  },
    { id: 'tools',    label: 'Tools',       icon: '🔧' },
    { id: 'wizard',   label: 'Wizard Steps',icon: '🧙' },
  ],

  async checkBackend() {
    try {
      const r = await fetch('/api/health')
      this.backendStatus = r.ok ? 'online' : 'offline'
    } catch {
      this.backendStatus = 'offline'
    }
  },

  init() {
    this.checkBackend()
    setInterval(() => this.checkBackend(), 10000)
  }
}))
```

### Section content — placeholder panels only

Each section shows a grey placeholder card with:
- Section title
- "Coming in Step X/4" subtitle
- A short description of what will be implemented

Example for Projects:
```html
<div class="placeholder-card">
  <h2>📁 Project Management</h2>
  <p class="coming">Implemented in Step 2/4</p>
  <p class="desc">Grid view of all pipeline projects with preview,
  delete, copy and step status editing.</p>
</div>
```

---

## HEALTH ENDPOINT — add to `backend/main.py`

```python
@app.get("/api/health")
async def health():
    return {
        "status": "online",
        "port": 8000,
        "wizard_url": "http://localhost:5173",
        "version": "1.0.0"
    }
```

---

## ACCEPTANCE CRITERIA

After this step:
- `http://127.0.0.1:8000/` shows the admin shell (not Hello World)
- All 4 nav items are clickable and switch the main panel
- Status bar shows "● Online" in green
- `http://127.0.0.1:8000/docs` still works (Swagger)
- `http://localhost:5173/` wizard is unaffected
