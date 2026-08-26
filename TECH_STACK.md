# Technical stack — 3DGS Pipeline App

> Companion to [CLAUDE.md](CLAUDE.md). That file is the **spec** (why the app is
> shaped the way it is); this one is the **inventory** (what is actually
> installed, pinned, imported and executed, as measured on the workstation).
>
> Measured on **2026-08-24**, branch `main`, on Windows 11 Pro 10.0.26200.
> Every version below was read from the installed environment, not from a
> manifest range. Where the two disagree, §12 says so.

---

## 1. Shape of the system

```
┌───────────────────────────────────────────────────────────────────────┐
│ Browser (localhost:5173)                                              │
│   React 18 SPA — Vite dev server, no SSR, no router                   │
└───────────┬──────────────────────────┬────────────────────────────────┘
            │ HTTP /api  (axios)       │ WS /ws/logs
            │ HTTP /static (files)     │
┌───────────▼──────────────────────────▼────────────────────────────────┐
│ FastAPI / Uvicorn (127.0.0.1:8000)                                    │
│   routes ──► pipeline_runner ──► core/steps/* ──► subprocess          │
│                    │                                                  │
│                    └── broadcast_fn ──► ConnectionManager ──► WS       │
└───────────┬───────────────────────────────────────────────────────────┘
            │ subprocess (never linked)
    ┌───────┴────────┬──────────────┬───────────────┬──────────────┐
    ▼                ▼              ▼               ▼              ▼
  FFmpeg        RealityScan    LichtFeld Studio   Blender      ffprobe
  8.1.1            2.2             v0.5.3          5.1
```

Two processes, one machine, one user, one job at a time. There is no broker, no
task queue, no cache server and no container. The only IPC is `subprocess` +
pipes, and the only realtime channel is a single WebSocket fan-out.

**Scale of the codebase** (excluding `node_modules/`, `.venv/`, `tools/`,
`projects/`):

| Side | Files | Lines |
|---|---|---|
| Backend (`backend/**/*.py`) | 38 | 7 931 |
| Frontend (`frontend/src/**/*.{ts,tsx}`) | 70 | 10 012 |

---

## 2. Runtime and toolchain

| Component | Version installed | Where it comes from |
|---|---|---|
| Python (venv interpreter) | **3.14.0** | `3dgs-pipeline-app/.venv/Scripts/python.exe` |
| Node.js | **24.12.0** | system |
| npm | **11.6.2** | system |
| Git | 2.53.0.windows.1 | used at runtime by `/api/version` |
| OS | Windows 11 Pro 10.0.26200 | the only supported target (§1 of CLAUDE.md: no VPS) |

The venv runs **Python 3.14**, while `requirements.txt` and `setup.py` both
declare a 3.11 floor (`setup.py` hard-exits below 3.11). 3.11+ is satisfied, so
nothing is broken — but the app is being exercised only on 3.14, and no other
interpreter has been tested against it.

**Windows-specific runtime detail** — [backend/main.py:8-11](3dgs-pipeline-app/backend/main.py#L8-L11)
forces `WindowsProactorEventLoopPolicy` before importing anything else. The
asyncio default on Windows is `SelectorEventLoop`, which does not support
subprocesses at all; without this line every step that spawns a tool fails.

---

## 3. Backend — Python

### 3.1 Declared dependencies

There are **two** requirements files and they are not the same file.

`3dgs-pipeline-app/requirements.txt` — the authoritative one, annotated, matching
CLAUDE.md §10:

| Package | Constraint | Role |
|---|---|---|
| `fastapi` | `>=0.115` | HTTP + WS framework |
| `uvicorn[standard]` | `>=0.30` | ASGI server (pulls `httptools`, `watchfiles`, `python-dotenv`, `PyYAML`, `colorama`) |
| `pydantic` | `>=2.7` | request/response models, settings validation |
| `sqlmodel` | `>=0.0.22` | project registry ORM (pulls SQLAlchemy) |
| `python-multipart` | `>=0.0.9` | multipart parsing for the video upload route |
| `websockets` | `>=12.0` | WS protocol implementation |
| `aiofiles` | `>=23.2` | async file IO |
| `httpx` | `>=0.27` | HTTP client |
| `watchdog` | `>=4.0` | `step_export`: watch `lfs_output/` for new PLY |
| `numpy` | `>=1.26` | score arrays, rolling medians |
| `scenedetect` | `>=0.6.4` | `AdaptiveDetector` cut detection |
| `opencv-python` | `>=4.9` | Tenengrad, ORB, HSV histograms |

`3dgs-pipeline-app/backend/requirements.txt` — a **stale duplicate**: older
floors, and it is missing `numpy`, `scenedetect` and `opencv-python` entirely.
It is not dead code — `setup.py` installs *this* one
([setup.py:36](3dgs-pipeline-app/setup.py#L36)), so a fresh `python setup.py`
produces a venv that cannot run wizard step 2. See §12.

### 3.2 What is actually installed

Resolved versions in `.venv`, which are well ahead of every floor:

```
fastapi          0.141.1      starlette      1.6.0        pydantic        2.13.4
uvicorn          0.52.4       h11            0.16.0       pydantic_core   2.46.4
websockets       17.0.1       httptools      0.8.0        anyio           4.14.2
sqlmodel         0.0.39       SQLAlchemy     2.0.52       greenlet        3.5.5
numpy            2.5.2        opencv-python  5.0.0.93     scenedetect     0.7.1
watchdog         6.0.0        watchfiles     1.2.0        aiofiles        25.1.0
httpx            0.28.1       httpcore       1.0.9        python-multipart 0.0.32
tqdm             4.70.0       PyYAML         6.0.3        python-dotenv   1.2.3
```

Two of these are worth flagging as majors crossed since the constraints were
written: **NumPy 2.5** (`>=1.26` was written for the 1.x API) and
**OpenCV 5.0** (`>=4.9`). Both are in use in the curation path.

> **The OpenCV wheel is deliberately the GUI build, not `-headless`.**
> PySceneDetect depends on `opencv-python`; both wheels install the same `cv2`
> package and cannot coexist, so the app takes the one its dependency asks for.
> Same Apache-2.0 licence; the GUI symbols simply go unused.

### 3.3 Module layout and the purity rule

```
backend/
├── main.py                     app assembly: event-loop policy, routers,
│                               mimetypes, /static mount, lifespan
├── api/
│   ├── websocket.py            ConnectionManager + broadcast(); the one bus
│   ├── file_handles.py         monkey-patch: AsyncFile.aclose() closes in place
│   └── routes/                 projects, pipeline, settings, defaults, files, version
├── core/
│   ├── config.py               config.json  — installation layer (exe paths)
│   ├── defaults.py             defaults.json — business layer + fps resolver
│   ├── probe.py                ffprobe wrapper (pure)
│   ├── proc.py                 subprocess registry, kill_tree, iter_lines
│   ├── ply.py                  PLY reader + .splat / .pc3d preview writer
│   ├── preview.py              which file a step produced + its cached preview
│   ├── cameras.py              transforms.json → camera poses for the overlay
│   ├── sources.py              input/ listing, find_extraction_source
│   ├── project_ops.py          copy / reset / archive / delete (no FastAPI)
│   ├── dep_manager.py          tool auto-detection and status
│   ├── pipeline_runner.py      orchestrator: step map, abort, settings overlay
│   ├── curate/                 sharpness, scenes, overlap, select  ← pure
│   └── steps/                  step_extract, step_analyze, step_rc, step_lfs,
│                               step_export, step_blender
│                               + colmap_dataset, rc_export_params,
│                                 rc_postprocess, rc_progress
├── db/database.py              engine, create_all, _add_missing_columns
├── models/                     project.py (SQLModel table), settings.py
└── scripts/blender_splatforge.py   runs *inside* Blender, imports bpy
```

**The purity rule is architectural, not stylistic** (CLAUDE.md §2.4):
`core/steps/` and `core/curate/` must not import FastAPI. They receive
`broadcast_fn` by dependency injection, which is what makes them callable from a
test without an ASGI app. Verified — no FastAPI import exists under either tree.

`backend/scripts/blender_splatforge.py` is the one file that is not part of the
app's own runtime: it imports `bpy` and executes inside Blender's embedded
Python, launched as `blender --background --python …`.

### 3.4 Subprocess handling — `core/proc.py`

Every external tool goes through one module, for three reasons that were each
found the hard way:

- **`spawn` / `release` register each child by project directory**, so
  `request_abort` can `taskkill /F /T` the whole tree. RealityScan and
  LichtFeld Studio both spawn workers; killing only the parent orphans the
  process that holds the GPU.
- **`kill_tree` is also what unblocks the reader.** The stdout reader thread
  sits in `readline()` on a pipe that only closes when the child dies.
- **`iter_lines` splits on CR as well as LF and strips ANSI SGR escapes.**
  FFmpeg, LichtFeld Studio and RealityScan all redraw a status line with a bare
  carriage return on a line that never terminates — `readline()` hands the whole
  run back as one line, at exit. Three occurrences of the same bug is why this
  is shared rather than copy-pasted.

A child killed this way raises `ProcessAborted`, which the runner maps to step
status `aborted` rather than `error`.

### 3.5 Persistence

**SQLite via SQLModel** — `3dgs-pipeline-app/pipeline.db`, one table:

| `project` column | Type | Note |
|---|---|---|
| `id` | str PK | `uuid4().hex[:8]` |
| `name`, `slug` | str | slug is unique against both DB and disk (`_unique_slug`) |
| `created_at`, `updated_at` | datetime | naive UTC — the frontend re-stamps `Z` before parsing |
| `current_step` | int | wizard position |
| `step_status` | str | JSON blob, accessed via `get_step_status()` / `set_step_status()` |
| `input_video_path`, `frame_count` | | |
| `settings_json` | str | **layer 3** of the settings model — only the keys this project overrides |
| `error_message` | str? | |
| `archived_at`, `archive_path` | | added post-release |

**Migrations are one `ALTER TABLE` each**, not Alembic.
`SQLModel.metadata.create_all` only creates missing *tables*, so columns added
later would be absent from an existing `pipeline.db` and every query on them
would fail with "no such column". `_add_missing_columns()` in
[db/database.py](3dgs-pipeline-app/backend/db/database.py) compares
`PRAGMA table_info` against a declared list and adds what is missing. Additive
changes only — anything a plain `ADD COLUMN` cannot express is the day this
becomes a real migration tool.

> The engine is created with `echo=True`, so every SQL statement is printed to
> the backend console. Convenient locally, noisy in the log.

**Per-frame data is JSON on disk, not SQL.** A project produces thousands of
frame records, written once per analysis run and read as a block:
`analysis/{probe,extract,scores,selection,overrides}.json`. They would buy
nothing from SQL but migrations.

---

## 4. Frontend — TypeScript / React

### 4.1 Runtime dependencies

| Package | Version | Role |
|---|---|---|
| `react` / `react-dom` | **18.2** | ⚠ 18, not 19 — see §12 |
| `zustand` | 4.5.2 | the single store (`store/pipelineStore.ts`) |
| `immer` | 11.1.8 | immutable store updates |
| `axios` | 1.6.8 | HTTP client (`api/client.ts`) |
| `recharts` | 3.8.1 | sharpness timeline, LFS training metrics |
| `@types/recharts` | 1.8.29 | ⚠ stale stubs for a v1 API — recharts 3 ships its own types |
| `three` | 0.169 | point-cloud renderer, camera overlay, OrbitControls |
| `@mkkellogg/gaussian-splats-3d` | 0.4.7 | depth-sorted, alpha-blended splat rasteriser |
| `radix-ui` + `@radix-ui/react-slot` | 1.4.3 / 1.0.2 | unstyled primitives under shadcn/ui |
| `lucide-react` | 0.378 | icons |
| `class-variance-authority`, `clsx`, `tailwind-merge` | | shadcn/ui variant plumbing |
| `tailwindcss-animate`, `tw-animate-css` | | animation utilities |
| `@fontsource-variable/geist` | 5.2.8 | self-hosted variable font |
| `shadcn` | 4.7.0 | ⚠ the **CLI**, listed as a runtime dependency — it generates components, it is not imported |

### 4.2 Build dependencies

| Package | Version |
|---|---|
| `vite` | 5.2 |
| `@vitejs/plugin-react` | 4.2.1 |
| `typescript` | 5.2 |
| `tailwindcss` | **4.0.0-alpha.13** (with `@tailwindcss/vite` 4.3.0) |
| `eslint` + `@typescript-eslint/*` | 8.57 / 7.2 |
| `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh` | 4.6 / 0.4.6 |
| `postcss`, `autoprefixer` | 8.4 / 10.4 |

Tailwind is pinned to an **alpha** of v4 while the Vite plugin is a stable 4.3 —
they are not the same release line. Tailwind v4 also does its own prefixing, so
`postcss` + `autoprefixer` are legacy entries from the v3 setup.

### 4.3 Source layout

```
frontend/src/
├── main.tsx / App.tsx
├── api/client.ts               axios instance + staticUrl()
├── store/pipelineStore.ts      zustand + immer; the WS reducer lives here
├── providers/SettingsProvider.tsx
├── hooks/                      useWebSocket, usePipeline, useProjects,
│                               useSettings, useDefaults, useCuration,
│                               usePreview, useSources, useProjectSettings,
│                               useVersion
├── pages/                      MainPage, SetupScreen
├── components/
│   ├── wizard/                 WizardShell, StepNav, steps/Step1…Step6
│   ├── settings/               AppSetupPanel (1 095 lines) + per-step panels
│   ├── panels/                 SourcePanel, VideoPlayerDialog, FrameGallery,
│   │                           SharpnessTimeline, LiveLog, ProgressBar, HelpPanel
│   ├── projects/               ProjectList, ProjectOperationDialog
│   ├── viewer/                 SceneViewer, PointCloudCanvas, SplatCanvas,
│   │                           cameraRig.ts, frame.ts, pointCloud.ts
│   └── ui/                     13 shadcn primitives
└── types/index.ts              466 lines — the shared contract with the API
```

There is **no router**. `MainPage` / `SetupScreen` and the six wizard steps are
switched from store state.

### 4.4 Vite configuration — three deliberate settings

[frontend/vite.config.ts](3dgs-pipeline-app/frontend/vite.config.ts):

- **`resolve.dedupe: ['react', 'react-dom']`** — a second React copy reached
  through a transitive path gets its own dispatcher, and every hook throws
  `dispatcher is null` once the two are mixed in one render.
- **`optimizeDeps.include`** pre-bundles every Radix entry point, `three`,
  `OrbitControls` and the splat library at server start. They are only reachable
  through lazily-loaded wizard steps, so Vite used to discover them mid-session,
  re-optimize and bump the `browserHash` — leaving an open tab holding modules
  from both passes.
- **`server.proxy`** forwards `/api`, `/static` (HTTP) and `/ws`
  (`ws: true`) to `http://localhost:8000`.

Path alias `@` → `./src`; TypeScript is strict.

---

## 5. External tools — invoked as subprocesses, never linked

| Tool | Version on this workstation | Invoked by | Path key |
|---|---|---|---|
| **FFmpeg** | 8.1.1-full_build (gyan.dev, gcc 15.2.0) | `step_extract` (incl. the `scdet` cut-detection branch, CLAUDE.md §6.6), `sources` (poster frames) | `ffmpeg_path`, `ffmpeg_hwaccel` |
| **ffprobe** | same build | `core/probe.py` | derived from `ffmpeg_path` |
| **RealityScan** | 2.2 (Epic Games) | `step_rc` | `rc_exe_path` |
| **LichtFeld Studio** | v0.5.3 | `step_lfs` | `lfs_exe_path` |
| **Blender** | 5.1 | `step_blender` | `blender_exe_path` |

Exactly four `cmd = [...]` construction sites exist, one per tool:
[step_extract.py:314](3dgs-pipeline-app/backend/core/steps/step_extract.py#L314),
[step_rc.py:610](3dgs-pipeline-app/backend/core/steps/step_rc.py#L610),
[step_lfs.py:86](3dgs-pipeline-app/backend/core/steps/step_lfs.py#L86),
[step_blender.py:50](3dgs-pipeline-app/backend/core/steps/step_blender.py#L50).

There is **no simulation layer**: no stub flag, no fake output. A missing or
misconfigured `.exe` fails the step with the path it looked for.

`tools/` holds a `LichtFeld-Studio-windows-v053` build and the `supersplat`
gitlink. It is gitignored — a fresh clone has neither, and the prebuilt binaries
are re-downloaded by hand (`slang-llvm.dll` alone is 105 MB, which GitHub
rejects outright).

### 5.1 Per-tool protocol notes

**FFmpeg** — extraction is one filter chain: `fps` gate → optional `mpdecimate`
→ `scale` last, so only surviving frames are resized. Both sides truncated even
(`trunc(iw*f/2)*2`); the mjpeg encoder writes yuvj420p and refuses an odd side.
Progress comes from `-progress pipe:1 -nostats`, newline-delimited `key=value`
blocks twice a second, `out_time_us` divided by `probe.json`'s `duration_s`.

**RealityScan** — driven by a `.rscmd` script generated per run from the
settings, never a static file. Application settings go in as `-set "key=value"`
(`sfmFeatureDetectionQuality`, `sfmMaxFeaturesPerMpx`, `sfmMaxFeaturesPerImage`,
`sfmImagesOverlap`) — the keys are enumerated in the installed help, not guessed.
The COLMAP export is RS's own exporter, driven by a generated export-params XML
(`rc_export_params.py`). Progress arrives via `-writeProgress <file> 1`, tailed
from `rc_output/rc_progress.txt` and weighted by the script just written
(`rc_progress.py`) — RS is a **GUI-subsystem binary**, so its stdout is not a
usable channel and `readline()` blocks until it exits.

**LichtFeld Studio** — v0.5.3 prints a CR-redrawn training bar with ANSI colour,
and **catches its own training exceptions and exits 0**. `step_lfs` therefore
fails on a `Training error:` line *and* on an output directory with no
`.ply`/`.splat`. The `cudaEventDestroy failed: driver shutting down` storm that
follows every exit is CUDA teardown noise, explicitly not fatal.

Only flags this build actually has reach `build_lfs_command` — an unknown verb
makes the exe exit non-zero — and two of them are negatives, which is where the
mapping stops being obvious. `--no-alpha-as-mask` accompanies `--mask-mode`
whenever the dataset carries mask files, because alpha-as-mask is *automatic*
for any RGBA image and outranks them (§7.5 of the spec). And
`--no-save-eval-images` is emitted when the **Save eval images** switch is off:
the build saves the GT-vs-render comparison PNGs by default during an `--eval`
run, into `lfs_output/eval_step_<N>/`. Both are sent only when they can mean
something — the mask flag only with masks present, the eval flag only inside
the `--eval` branch.

**Blender** — `--background --python backend/scripts/blender_splatforge.py --`,
custom args after the `--` separator.

---

## 6. Realtime — one WebSocket, one reducer

`/ws/logs`, a plain fan-out: `ConnectionManager` holds a list of sockets,
`broadcast_json` sends to each and drops the ones that raise. No rooms, no
subscriptions, no backpressure, no persistence — a client that reconnects has
missed what it missed.

`broadcast()` types each message by **priority**, `status` → `metric` →
`file_ready` → `progress` → `log`:

```json
{ "type": "progress", "step": "extract", "timestamp": "…Z",
  "level": "info", "message": "…", "progress": 0.42,
  "data": {}, "file": "…", "status": "…" }
```

**The type does not decide which fields may be read.** The store reads
`progress` *above* the `switch`, for every type — an LFS line carries both a
metric and a position, and the type says what a message is mainly about, not
what it contains. Reordering the priority would have been the wrong fix.

The frontend side is `useWebSocket` (with a `mountedRef` guard so React
StrictMode's cleanup→remount cycle does not open a second connection, and 5
retries), reducing into `pipelineStore`.

Two pseudo-steps travel on the same bus without being wizard steps: `curate`
(step 2's second phase, mapped onto step 2) and `project` (copy / archive /
restore progress, routed to the modal dialog instead of to `stepProgress`).

---

## 7. Configuration — three layers, explicit precedence

| Layer | Store | Contents | Route |
|---|---|---|---|
| **Installation** | `config.json` | 6 keys: `rc_exe_path`, `lfs_exe_path`, `ffmpeg_path`, `ffmpeg_hwaccel`, `blender_exe_path`, `supersplat_url` | `/api/settings` |
| **Defaults** | `defaults.json` | `schema_version: 1` + 7 sections: `extract`, `curate`, `rc` (incl. nested `colmap.undistort`), `lfs`, `export`, `blender`, `viewer` | `/api/defaults` |
| **Per project** | `Project.settings_json` | only the keys this project overrides | `PATCH /api/projects/{id}` |

**Precedence: per-project > defaults > code fallback.** A project stores a
*diff* (`deepDiff` on the frontend, `_with_project_settings` overlay on the
backend), never a full copy — a full copy would stop a changed default from
propagating to existing projects.

`useProjectSettings(projectId, section, defaults[section])` is the single
frontend path: it reads the project's overrides, shows the defaults under them,
and PATCHes back the diff. There is no Save button — a 300 ms debounce
coalesces a slider drag and is flushed on unmount, on project switch (the patch
is tagged with the id it was typed against) and on `beforeunload` via a
`keepalive` fetch. A failed PATCH puts its patch back.

`supersplat_url` is **dead configuration** — it points at the public SuperSplat
editor, which cannot reach a local file. The in-app three.js viewer replaced it;
the key is still written and still read by the settings panel.

---

## 8. HTTP surface

39 route handlers across 6 routers, all under `/api`, plus the static mount.

```
projects   POST /create · GET / · GET /{id} · PUT /{id} · PATCH /{id} · DELETE /{id}
           POST /{id}/copy · /reset · /archive · /unarchive
           GET  /{id}/input-files · POST /{id}/upload-input
           DELETE /{id}/input-files/{filename}
pipeline   POST /start · /control · /analyze · GET /status
settings   GET / · PUT /
defaults   GET / · PUT / · POST /reset · GET /presets · POST /fps-preview
files      GET  /{id}/probe · /sources · /analysis · /alignment · /frames
                 /export · /preview · /cameras
           POST /{id}/preview · DELETE /{id}/frames
version    GET /
ws         /ws/logs
static     /static/<slug>/…   →  projects/
```

Two of these are undocumented in CLAUDE.md §8: `POST /api/defaults/fps-preview`
and `DELETE /api/files/{id}/frames`.

**`POST /{id}/preview` returns immediately and is polled through the GET** —
converting five million gaussians is seconds, and a request held open for the
length of it is indistinguishable from a hung app. It is deliberately outside
`pipeline_runner`: no external tool, no process to kill, and cancelling it would
only leave a `.part` behind.

`/api/version` shells out to `git` (`rev-parse`, `log -1`), cached once per
process, and derives the version as the commit date `YYYY.MM.DD`. No git, no
version — `"0.0.0"` would be inventing one. `CREATE_NO_WINDOW` keeps a console
from flashing on Windows.

---

## 9. Binary formats the app defines or rewrites

The 3D viewer never loads a step's output directly — measured, `rc_output/pointcloud.ply`
is 18–142 MB of **ASCII** and `lfs_output/splat_*.ply` has reached **1.24 GB**
(5 M gaussians with 45 SH coefficients a preview never uses).

| Source kind | Detected by | Preview | Record | Renderer |
|---|---|---|---|---|
| gaussians | `f_dc_*`, `opacity`, `scale_*`, `rot_*` | `.splat` | 32 B — pos, `exp(scale)`, SH-DC colour × `sigmoid(opacity)`, quantised quaternion | `@mkkellogg/gaussian-splats-3d` |
| plain cloud | everything else | `.pc3d` (ours) | 16 B — 3 × float32 + rgba, 16 B header, magic `PC3D` | `THREE.Points` |

- **The renderer is chosen from what the file *is*, not from which step asked.**
- **Decimation is a uniform spread, never a head slice** — a PLY is not
  shuffled, and the first million points of an RS cloud are one corner of the
  scene claiming to be the scene.
- **SH DC → colour goes through `SH_C0 = 0.28209479177387814`.** Skipping it is
  the classic washed-out preview.
- **Previews are fingerprinted, never overwritten**: the name carries 8 hex of
  the source's mtime+size (`rc_1000000_3d67781a.pc3d`), so a rebuild writes a
  new name instead of replacing a file somebody is reading — and the browser
  cannot serve the previous cloud from cache.

`.splat`, `.pc3d` and `.ply` are registered as `application/octet-stream` in
`main.py`; `StaticFiles` serves unknown extensions as `text/plain`, which invites
anything in the path to re-encode a binary splat as text.

**`api/file_handles.py` monkey-patches `anyio.AsyncFile.aclose()` to close in
place.** Starlette streams static files through `AsyncFile`, whose `aclose()` is
a *thread* call starting with a cancellation checkpoint — so any aborted download
(and `PointCloudCanvas` aborts its fetch on every level change and unmount,
StrictMode's double-mount included) unwound before the close and leaked the
handle until the server exited. On Windows that handle blocks the rename, the
delete and the project reset. Closing a file is a syscall, not blocking IO worth
a worker thread, and inline it cannot be cancelled.

---

## 10. Coordinate frames — three conventions in one pipeline

This is stack surface because it is where the tools disagree, and every
disagreement is a silent one.

| Frame | Who | Convention |
|---|---|---|
| RealityScan native | `pointcloud.ply` as exported | Z-up |
| NeRF / OpenGL | `transforms.json`, three.js | Y-up |
| COLMAP | `sparse/0/`, LFS's preferred loader | its own |

- `rc_postprocess.py` rotates the sparse cloud `Rx+90`, `(x,y,z) → (x,−z,y)`,
  stamped in the PLY header so a re-run is a no-op. It also hoists median
  `PINHOLE` intrinsics to the top level and relativises the image paths —
  without which LFS logs `No camera intrinsics found, assuming equirectangular`,
  refuses to train, **and exits 0**.
- That `Rx+90` sends RS's +Z onto **−Y**, so `viewer/frame.ts` rotates RS-frame
  content 180° around X **per object, not per step** — the `rc` preview *and*
  the camera overlay in all three viewer steps. LFS applies its own `Rx+180`
  when reading NeRF transforms, so the trained splat needs nothing.
- The COLMAP export is written with `scene_rotate_x_deg: 180`, which composes
  with RS's hard-coded `Rx+90` to `Rx−90` overall and lands both routes in the
  same world frame.

It is a display transform. Nothing on disk moves.

---

## 11. Licensing posture

Audited as if the tool could be distributed tomorrow. The four heavy tools are
invoked as **subprocesses, never linked**, which is what keeps RealityScan's
proprietary licence and Blender's GPL out of this codebase's obligations.

| Group | Licence |
|---|---|
| FastAPI, Uvicorn, Pydantic, SQLModel, aiofiles, httpx | MIT / BSD-3 |
| websockets, watchdog | BSD / Apache-2.0 |
| NumPy, PySceneDetect | BSD-3 |
| OpenCV (`opencv-python`) | Apache-2.0 |
| React, Vite, Tailwind, shadcn/ui, Zustand, recharts, immer, axios | MIT |
| three.js, `@mkkellogg/gaussian-splats-3d` | MIT |
| Geist (`@fontsource-variable/geist`) | OFL-1.1 |
| FFmpeg (system exe) | LGPL-2.1+ — **GPL if built with x264**; re-audit before any distribution |
| RealityScan / LichtFeld Studio / Blender | proprietary / GPL, external, subprocess only |

Any new dependency gets a row in CLAUDE.md §10 **in the same commit**.

---

## 12. Where the stack drifts from the spec

Measured, not inferred. None of these is currently breaking the app on this
workstation; all of them are traps for the next change or the next clone.

| # | Drift | Consequence |
|---|---|---|
| 1 | **`backend/requirements.txt` is a stale duplicate** missing `numpy`, `scenedetect`, `opencv-python` — and `setup.py:36` installs *that* file | A fresh `python setup.py` builds a venv where wizard step 2 cannot import `cv2`. The root `requirements.txt` is the correct one |
| 2 | **`api/client.ts` hardcodes `http://localhost:8000/api`** and **`useWebSocket.ts` hardcodes `ws://localhost:8000/ws/logs`** | CLAUDE.md's 2026-08-22 row records these as made origin-relative; they are not. Opening the app from another machine on the LAN gives a blank wizard and a dead log bus. It also bypasses the `/api` and `/ws` proxies Vite already declares |
| 3 | **`vite.config.ts` has no `server.host: true`** | Same row claims it was added. The dev server is loopback-only, so #2 is currently unobservable — the two defects mask each other |
| 4 | **Port is 8000 everywhere** (`main.py`, `start.bat`, `start.sh`, vite proxy, client) | CLAUDE.md's 2026-08-22 row says 8010. 8000 is the truth |
| 5 | **Venv runs Python 3.14**, manifests declare a 3.11 floor, CLAUDE.md §3 says "3.11+" | Satisfied, but only 3.14 is exercised |
| 6 | **NumPy 2.5 against a `>=1.26` floor; OpenCV 5.0 against `>=4.9`** | Two majors crossed under the constraint. The curation path is the code that would notice |
| 7 | **`tailwindcss` pinned to `4.0.0-alpha.13`** while `@tailwindcss/vite` is 4.3.0 | An alpha in a build path, and the two are not the same release line |
| 8 | **`postcss` + `autoprefixer` still declared** | Legacy v3 entries; Tailwind v4 does its own prefixing |
| 9 | **`shadcn` (the CLI) is a runtime dependency**, and `@types/recharts@1.8.29` types a v1 API against recharts 3 | Both ship in `dependencies` without being imported / being correct |
| 10 | **React is 18.2, and shadcn's current docs emit React 19 components** | A v19 component takes `ref` as a plain prop, which React 18.3 *strips*. `ui/button.tsx` is wrapped in `forwardRef` for exactly this reason — every component pasted from the v4 docs needs the same treatment until React is upgraded, or Radix gets no anchor and parks its popper off-screen at `translate(0,-200%)` |
| 11 | **`create_engine(..., echo=True)`** | Every SQL statement printed to the backend console |
| 12 | **CORS in `main.py` allows `:5173` explicitly** | Moot if everything were same-origin, live because of #2. Left as-is rather than widened |
| 13 | **`supersplat_url` is dead config** | Written, read by the settings panel, used by nothing |
| 14 | **Two API routes are undocumented** — `POST /api/defaults/fps-preview`, `DELETE /api/files/{id}/frames` | CLAUDE.md §8 is incomplete |

---

## 13. Running it

```bat
:: from 3dgs-pipeline-app/
start.bat
```

Which is two detached processes:

```bat
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
cd frontend && npm run dev          :: vite on :5173
```

`start.sh` is the POSIX equivalent and additionally opens the browser.
First-time provisioning is `python setup.py` — venv, pip install, `npm install`,
and a git clone of LichtFeld Studio into `tools/` — **subject to drift #1**.

Frontend scripts: `dev`, `build` (`tsc && vite build`), `lint`
(`--max-warnings 0`), `preview`.

**`projects/` is sacred** — it holds all user data and must never be touched by
a clean or reset script. `preview/` inside it is a cache, safe to delete at any
time, and costs one rebuild.
