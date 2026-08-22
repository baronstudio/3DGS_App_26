# DEVELOPING — 3DGS Pipeline App

Working notes for whoever is inside the code. The user-facing documents are
[README.md](README.md) (what this is) and
[3dgs-pipeline-app/README.md](3dgs-pipeline-app/README.md) (install and use).
This one assumes you have both installed and running.

**[CLAUDE.md](CLAUDE.md) is the specification and it outranks this file.** Read
it before changing anything structural — in particular §12, the dated decisions
log, which records why each non-obvious choice was made. Every new structural
decision gets a row there in the same commit.

---

## 1. Shape of the thing

Two servers, started together by `start.bat`:

| Part | Runs | Port |
|---|---|---|
| Backend | `uvicorn backend.main:app --reload` under `3dgs-pipeline-app/.venv` | 8000 |
| Frontend | `vite` in `3dgs-pipeline-app/frontend/` | 5173 |

Vite proxies `/api`, `/static` and `/ws` to 8000 (`frontend/vite.config.ts`), so
**always work against 5173**. Hitting 8000 directly gets you the API with no app
around it.

Everything the app does to the outside world is a subprocess: FFmpeg,
RealityScan, LichtFeld Studio, Blender. Nothing is linked, nothing is vendored
into the repo, and there is no simulation layer — a misconfigured `.exe` fails
its step with the path it looked for.

> **RS** is RealityScan, and it is abbreviated that way in the docs and in every
> string the user sees — UI labels, the `[RS]` log prefix, error messages.
>
> The *identifiers* still say `rc` and are meant to: `rc_output/`, `rc_exe_path`,
> `step_rc.py`, `rc_postprocess.py`, `RCSettings.tsx`, `Step3_RC.tsx`, the `rc`
> WebSocket step name, the `rc.*` settings keys. Renaming those is a migration —
> project directories on disk, `settings_json` keys in every existing project,
> the step name the store routes on — not a find-and-replace.
>
> Two literals must never be renamed even though they read like prose:
> `_ROTATED_MARKER` in `rc_postprocess.py`, which is written into the PLY header
> and is how a re-run knows the cloud is already rotated (rename it and the next
> run rotates it twice), and the legacy `RealityCapture.exe` glob in
> `dep_manager.py`, which is a real filename on pre-2.0 installs.

---

## 2. Backend map

```
backend/
├── main.py                   FastAPI app: routers, /static mount, startup sweep
├── api/
│   ├── websocket.py          the /ws/logs broadcast bus
│   ├── file_handles.py       StaticFiles close patch (see §6)
│   └── routes/               projects · pipeline · settings · defaults · files
├── core/
│   ├── config.py             config.json     → AppConfig
│   ├── defaults.py           defaults.json   → AppDefaults + the fps resolver
│   ├── pipeline_runner.py    the orchestrator: step dispatch, abort, status
│   ├── proc.py               child-process registry + taskkill /F /T
│   ├── probe.py              ffprobe wrapper (pure)
│   ├── ply.py                PLY streaming → decimated .splat / .pc3d
│   ├── preview.py            preview cache: build, fingerprint, prune
│   ├── cameras.py            transforms.json → camera overlay payload
│   ├── project_ops.py        copy / reset / archive / restore / delete
│   ├── dep_manager.py
│   ├── steps/                step_extract · step_analyze · step_rc · step_lfs
│   │                         step_export · step_blender
│   │                         + rc_postprocess · rc_export_params
│   └── curate/               sharpness · scenes · overlap · select
├── db/database.py            SQLite engine, create_all, _add_missing_columns
├── models/                   project.py (SQLModel) · settings.py
└── scripts/blender_splatforge.py    runs inside Blender, not in the venv
```

### The rule that shapes it

**`core/steps/` and `core/curate/` must not import FastAPI.** They take
`broadcast_fn` by injection. That is the whole reason they are testable against
a temp directory with no server running, and it is easy to break by reaching for
`HTTPException` in a step. Raise a plain exception and let the route translate
it. `core/project_ops.py` follows the same rule for the same reason.

### Persistence is deliberately split

- **SQLite (`pipeline.db`)** holds the project registry only: name, slug,
  current step, per-step status, `settings_json`, archive fields.
- **JSON under `projects/<slug>/analysis/`** holds per-frame data. A project
  produces thousands of frame records, written once per run and read as a block.
  In SQL they would buy nothing but migrations.

| File | Contents |
|---|---|
| `probe.json` | raw ffprobe output of the source, nothing else |
| `extract.json` | what extraction *actually did*: resolved fps, source path, mpdecimate flag, frame count |
| `scores.json` | per frame: index, filename, sharpness, displacement, sequence id |
| `selection.json` | kept / rejected with reasons — regenerated every analysis |
| `overrides.json` | manual keep/drop — **never** regenerated, always wins |

`extract.json` is separate from `probe.json` on purpose: curation needs the
*resolved* working fps to map a cut timecode onto a frame index, and needs to
know whether `mpdecimate` broke that mapping.

### Schema changes

`SQLModel.metadata.create_all` only creates missing *tables*, so a new column
never appears in an existing `pipeline.db`. `_add_missing_columns()` in
`db/database.py` compares `PRAGMA table_info` against a declared list and issues
one `ALTER TABLE ADD COLUMN` per missing field. One user, one file, additive
changes only — the day a change cannot be expressed as a plain `ADD COLUMN` is
the day this needs a real migration tool.

---

## 3. Frontend map

```
frontend/src/
├── main.tsx · App.tsx
├── api/client.ts             axios instance
├── store/pipelineStore.ts    Zustand: the single source of wizard truth
├── hooks/                    useWebSocket · usePipeline · useProjects
│                             useSettings · useDefaults · useCuration · usePreview
├── providers/SettingsProvider.tsx
├── pages/                    SetupScreen · MainPage
└── components/
    ├── wizard/               WizardShell · StepNav · steps/Step1…Step6
    ├── panels/               LiveLog · ProgressBar · FrameGallery · SharpnessTimeline · HelpPanel
    ├── projects/             ProjectList · ProjectOperationDialog
    ├── settings/             AppSetupPanel · SettingsDrawer · {FFmpeg,Curate,RC,LFS}Settings
    ├── viewer/               SceneViewer · PointCloudCanvas · SplatCanvas
    │                         cameraRig.ts · frame.ts · pointCloud.ts
    └── ui/                   shadcn primitives
```

React 18 + TypeScript strict, Tailwind v4, path alias `@/` → `src/`.

**There is one project list.** `components/projects/ProjectList.tsx` is rendered
by step 1 in both of its modes (embedded, without its Card chrome). It used to
have a read-only twin inside the step, which meant options added to one list
were options the user could not find.

---

## 4. The WebSocket bus

Everything long-running reports on `/ws/logs`. Messages carry a step name; the
store routes on it:

| Step name | Routed to |
|---|---|
| `extract`, `rc`, `lfs`, `export`, `blender` | that wizard step's progress |
| `curate` | mapped onto **step 2** — one job, two phases, two bars, no seventh step |
| `project` | the blocking `ProjectOperationDialog`, **not** `stepProgress` — copy/archive/restore are not wizard steps |

Copy, archive and restore run in a worker thread and report every 20 files
*plus* every file over 8 MB. Neither rule alone covers a project of five 1 GB
splats.

---

## 5. Running a step

`pipeline_runner.py` maps step numbers to runners (`_STEP_NAMES`,
`_STEP_RUNNERS`) and each `/api/pipeline/start` call runs exactly **one** step.
Step 2 is one job with two phases: extraction, then analysis — and the analysis
is re-runnable alone through `/api/pipeline/analyze`, because tuning a threshold
must never cost a re-extraction.

### Abort

Abort is not "cancel the coroutine". Every exe step streams stdout from a
thread-pool `readline()`, so cancelling the task unwinds the Python side and
leaves the tool running on the GPU with nothing referencing it, and the reader
thread blocked on a pipe that never closes.

`core/proc.py` registers every child by project directory, and `request_abort`
`taskkill /F /T`s the **tree** — RS and LFS spawn workers, so killing the parent
alone orphans the process that actually holds the GPU. Killing it is also what
closes the pipe and unblocks the reader. A child killed that way raises
`ProcessAborted`, handled like `AnalysisAborted`: the step ends `aborted`, not
`error`.

Two things that bite:

- `asyncio.CancelledError` derives from `BaseException`. An `except Exception`
  never sees it, and the step stays "running" in the UI until a reload. It is
  caught by name.
- **Pause does not exist.** The event was only awaited *between* steps, and
  `/start` runs one step per call, so no running step ever observed it. None of
  the three tools has a pause verb either. Reviving it means suspending the
  child process or threading the event into the curation loops — a feature, not
  a wiring fix.

On startup, `reconcile_orphaned_steps()` sweeps any step still persisted as
`running`: it belongs to a process this one never started, and it would freeze
that step's button forever.

### A zero exit code is not success

LichtFeld Studio v0.5.3 catches its own training exceptions, logs
`Training error: …` and **exits 0**. `step_lfs.py` therefore fails on that line
*and* on an output directory containing no `.ply`/`.splat`. The
`cudaEventDestroy failed: driver shutting down` storm that follows every exit is
CUDA teardown noise and is explicitly not fatal — it is the symptom, never the
cause.

The same suspicion applies elsewhere: prefer checking what a tool *produced*
over what it returned.

---

## 6. Things that will surprise you

### The two frames of reference

This is the single most confusing area in the codebase; §7.2 and §7.3 of
CLAUDE.md are the long version.

RealityScan's two exporters disagree with each other, and neither writes what
the LichtFeld Studio loader reads. `rc_postprocess.py` (gated on
`rc.normalise_for_lfs`) rewrites both after alignment: it hoists median PINHOLE
intrinsics to the top level, relativises the image paths, and rotates the sparse
cloud by `Rx+90` so cloud and cameras agree.

That rotation leaves the whole RS frame **Y-down**. LichtFeld Studio's NeRF
loader then applies its own `Rx+180` when reading the transforms, so the trained
splat comes out Y-up and needs nothing. Hence: the viewer rotates **per object,
not per step** (`viewer/frame.ts`) — RS-frame content (the `rc` preview *and* the
camera overlay in all three steps) is turned 180° around X for display; LFS-frame
content is not. It is a display transform; nothing on disk moves.

Correcting `rc_postprocess` instead would only move the problem: LFS would then
train Y-down and step 4 would be the broken one.

### The preview cache

Previews are never overwritten. The filename carries an 8-hex fingerprint of the
source's mtime and size (`rc_1000000_3d67781a.pc3d`), so a new revision writes a
new name instead of replacing a file somebody may be reading. Older revisions of
the same (source, level) are pruned best-effort after each build.

That is not tidiness. `StaticFiles` streams through `anyio.AsyncFile`, whose
`aclose()` starts with a cancellation checkpoint — so any aborted download
(`PointCloudCanvas` aborts its fetch on every level change and unmount, React
StrictMode's double-mount included) unwinds *before* the close and leaks the
handle until the server exits. On Windows that handle blocks the rename, the
delete, and the project reset. `api/file_handles.py` patches `aclose()` to close
in place; the fingerprinted name is the belt to that braces, and it also stops
the browser serving the previous cloud from cache.

### shadcn components need `forwardRef`

This app is **React 18**. Components pasted from the shadcn v4 docs are the
React 19 flavour — a plain function taking `ref` as a prop — and React 18.3
strips that ref. Radix then has no anchor element, and an unanchored Popper
parks its content at `translate(0, -200%)`, off the top of the page. The menu
opens perfectly, where nobody can see it. `ui/button.tsx` is wrapped; anything
new from those docs needs the same treatment until React is upgraded.

### Windows event loop

`main.py` forces `WindowsProactorEventLoopPolicy` before importing anything
else. The default selector loop does not support subprocesses, which is most of
what this app does.

### Console encoding

A French Windows console is cp1252 and has no mapping for the arrows the debug
lines use. The resulting `UnicodeEncodeError` propagates out of the caller — it
once killed the abort handler mid-way and left the step "running". `_debug()`
swallows it: a debug line is never worth an exception.

---

## 7. Known traps

Real, currently true, and each one has cost time:

| Trap | Detail |
|---|---|
| **`setup.py` destroys a working `config.json`** | It writes `{"tools": {…}}`, but `load_config()` reads flat top-level keys. Re-running setup leaves a file the app parses to all-empty paths. Fix the script or do not run it twice. |
| **Two `requirements.txt`** | `3dgs-pipeline-app/requirements.txt` is current; `backend/requirements.txt` is an older copy with no numpy, opencv or scenedetect — and `setup.py` installs *that* one. |
| **`setup.py` still clones SuperSplat** | The SuperSplat route was dropped on 2026-08-20 (the viewer is in-app). The clone is dead weight, and `supersplat_url` is a dead key kept only by the settings model. |
| **`.venv/Scripts/activate.bat` may hold a stale path** | If the checkout ever moved drive, the hardcoded `VIRTUAL_ENV` sends you to the *global* Python, and the backend dies on `ModuleNotFoundError: No module named 'sqlmodel'`. Never activate — call `.venv\Scripts\python.exe -m …` directly, which is what `start.bat` does. `Activate.ps1` derives its path at runtime and is unaffected. |
| **`frontend/src/api/client.ts` hardcodes `http://localhost:8000`** | The one hygiene rule kept from the dropped remote-deployment track. `useDefaults` already uses relative `/api/…` through the Vite proxy; the axios client should too. |
| **`rc.colmap.scene_rotate_x_deg` is `0.0` in `defaults.json`** | CLAUDE.md and TODO.md both call for `180` — without it the COLMAP path trains a splat upside down relative to today's. The COLMAP export has not been run against real RealityScan yet (TODO P1), so this may simply be untouched rather than decided. Confirm before trusting either value. |
| **RS is fed the whole `frames/` directory** | Curation verdicts included: frames step 2 rejected still go into `-align`. Possibly deliberate (more frames, better odds of a single component) but nowhere stated in the UI. |
| **RS precision / max features are not applied** | They exist in `defaults.json` and the step 3 Advanced panel, but `build_rscmd()` emits neither — the app models no verb for them. `rc.extra_align_commands` is the escape hatch. |

---

## 8. Working on it

### Run

```powershell
cd 3dgs-pipeline-app
.\start.bat
```

Or by hand, two terminals — backend first:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
cd frontend ; npm run dev
```

### Check

```powershell
# backend imports cleanly, no server needed
.\.venv\Scripts\python.exe -c "from backend.main import app"

# FastAPI's own docs — every route, live
curl http://127.0.0.1:8000/docs

# frontend
cd frontend ; npm run build   # tsc + vite build
cd frontend ; npm run lint    # eslint, --max-warnings 0
```

A port already in use means a previous run is still alive:

```powershell
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen | Select-Object LocalPort,OwningProcess
```

### API surface

```
GET    /api/projects                   list          POST   /api/projects            create
GET    /api/projects/{id}              one           PATCH  /api/projects/{id}       deep-merged settings + overrides
DELETE /api/projects/{id}              row + directory + archive
POST   /api/projects/{id}/copy         duplicate     POST   /api/projects/{id}/reset  wipe steps, keeps input/
POST   /api/projects/{id}/archive      zip away      POST   /api/projects/{id}/unarchive
POST   /api/pipeline/start             one step      POST   /api/pipeline/control     pause / resume / abort
GET    /api/pipeline/status                          POST   /api/pipeline/analyze     curation alone, never re-extracts
GET    /api/settings/                  config.json   PUT    /api/settings/
GET    /api/defaults/                  defaults.json PUT    /api/defaults/            deep-merge
POST   /api/defaults/reset             factory reset (?section=)
GET    /api/defaults/presets           capture presets
GET    /api/files/{project}/frames     frames + verdicts
GET    /api/files/{project}/analysis   scores + selection + overrides
GET    /api/files/{project}/probe      ffprobe metadata
GET    /api/files/{project}/alignment  coverage report
GET    /api/files/{project}/preview    preview state (?source=rc|lfs|export&max_count=)
POST   /api/files/{project}/preview    build it — returns at once, poll the GET
GET    /api/files/{project}/cameras    camera poses for the overlay
WS     /ws/logs                        progress, logs, metrics
GET    /static/<slug>/...              project files
```

The preview build is a POST that **returns immediately** and is polled through
the GET: converting five million gaussians takes seconds, and a request held
open that long is indistinguishable from a hung app. It sits deliberately
outside `pipeline_runner` — nothing it runs is an external tool, there is no
process to kill, and cancelling it would only leave a `.part` file behind.

---

## 9. Conventions

- **Commits:** conventional commits (`feat:`, `fix:`, `chore:`, `docs:`), English.
- **Code:** identifiers and docstrings in English. Comments in French are fine.
- **Python:** type hints everywhere. No FastAPI import in `core/steps`,
  `core/curate` or `core/project_ops`.
- **TypeScript:** strict, `@/` → `src/`.
- **UI language:** English throughout. Do not mix until a deliberate switch.
- **Dependencies:** every new one is justified *and* added to the licence audit
  table (CLAUDE.md §10) in the same commit. Audit as if the app could be
  distributed tomorrow.
- **Structural decisions:** a row in CLAUDE.md §12, same commit, with the *why*.

### What is not in the repo

`node_modules/`, `.venv/`, `__pycache__/`, `frontend/dist/` and
`3dgs-pipeline-app/tools/` are gitignored — they were committed by the initial
import, at 27 393 tracked files of which 27 096 were artefacts. A fresh clone
therefore has **no vendored binaries**: LichtFeld Studio ships a 105 MB
`slang-llvm.dll`, over GitHub's hard limit. Bootstrap them yourself.

`3dgs-pipeline-app/projects/` is ignored and sacred: it holds user data and no
clean or reset script may touch it.

---

## 10. The other documents

| File | What it is |
|---|---|
| [CLAUDE.md](CLAUDE.md) | the specification, and the decisions log. The authority |
| [TODO.md](TODO.md) | prioritised backlog — what comes next, and what was deliberately left open |
| [README.md](README.md) | repository entry point |
| [3dgs-pipeline-app/README.md](3dgs-pipeline-app/README.md) | install, configure, run, use |
| `SESSION *.md`, `admin_step*.md`, `3dgs_webapp_prompt.md` | historical build notes from the original construction sessions. Kept for archaeology; **not** current documentation, and where they disagree with CLAUDE.md they are simply old |
