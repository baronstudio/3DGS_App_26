# CLAUDE.md — 3DGS Pipeline App

> Local-first web app that drives a full video → 3D Gaussian Splatting pipeline:
> import a video, extract + curate frames, align in RealityScan, train in LichtFeld
> Studio, export the splat, assemble the Blender scene.
>
> Owner: JB (baronstudio). Single user, Windows workstation, local GPU.

---

## 1. What this app is

A 6-step wizard (React) driving a FastAPI backend that orchestrates local `.exe`
tools as subprocesses:

```
video ─> [2] extract + curate ─> [3] RealityScan ─> [4] LichtFeld Studio ─> [5] export ─> [6] Blender
```

The **curation** part of step 2 (blur rejection, cut detection, overlap gate) comes
from the former standalone "FrameGate" spec, merged into this app on 2026-08-20.
See §6 and the decisions log (§12).

### Non-goals

- No multi-user, no auth, no job queue. One user, one running job at a time.
- **No VPS / remote deployment, ever.** This app drives RealityScan, LichtFeld
  Studio and Blender — local Windows binaries needing a local GPU. The FrameGate
  "VPS-ready" requirement is dropped. Only hygiene kept: no hardcoded `localhost`
  in the frontend API client.
- No 3D viewer beyond the existing PLY preview.

---

## 2. Core principles (do not violate)

1. **No superfluous dependencies.** Every new dependency is justified and added to
   the licence audit table (§10) in the same commit.
2. **Stub-driven development.** Each external tool has its own stub flag in
   `config.json` (`ffmpeg_stub`, `rc_stub`, `lfs_stub`, `blender_stub`) so the UI
   and pipeline are testable without GPU or installed tools.
3. **`projects/` is sacred.** `3dgs-pipeline-app/projects/` holds all user data and
   must NEVER be touched by a clean or reset script.
4. **Pipeline steps are pure-ish.** Modules under `backend/core/steps/` and
   `backend/core/curate/` must not import FastAPI. They receive `broadcast_fn` by
   injection — keep it that way; it is what makes them callable from tests.
5. **Simplicity over throughput.** A handful of videos per session. No queues, no
   worker pools, no caching layers "for later".
6. **Every job is cancellable.** `request_abort` / `request_pause` in
   `pipeline_runner.py` must be honoured by every long loop.

---

## 3. Stack

| Layer | Choice | Note |
|---|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn | `backend/main.py`, `.venv` at app root |
| Persistence | SQLite + SQLModel (`pipeline.db`) for projects | **JSON files** for per-frame data (§5) |
| App config | `config.json` — tool paths + stub flags | Route `/api/settings` |
| App defaults | `defaults.json` — per-step business defaults | Route `/api/defaults` (§4) |
| Realtime | **WebSocket** `/ws/logs` (`backend/api/websocket.py`) | SSE from the FrameGate spec is dropped — the WS bus is already wired end to end |
| Video | FFmpeg + ffprobe (system exe, subprocess) | Path in `config.json` |
| Curation | OpenCV (Tenengrad, ORB) + NumPy + PySceneDetect | Added with the FrameGate merge |
| Alignment | RealityScan CLI | `step_rc.py` |
| Training | LichtFeld Studio CLI | `step_lfs.py` |
| Scene | Blender + `blender_splatforge.py` | `step_blender.py` |
| Frontend | React 18 + TS, Vite, Tailwind v4, shadcn/ui, Zustand, recharts | `frontend/` |
| Run | `start.bat` (Windows) / `start.sh` | Not a Makefile — this is a Windows-first app |

---

## 4. Settings model — three layers, explicit precedence

Three distinct things, three homes. Do not merge them.

| Layer | File / store | Contents | UI |
|---|---|---|---|
| **Installation** | `config.json` | `.exe` paths, URLs, stub flags | Setup panel → "Tools & stubs" |
| **Defaults** | `defaults.json` | Business defaults per wizard step (fps policy, curation thresholds, RC precision, LFS iterations…) + capture presets | Setup panel → one section per step |
| **Per project** | `Project.settings_json` (SQLite) | What the user changed for THIS project | Wizard step "Advanced" panels |

**Precedence: per-project > defaults > code fallback.** A project stores only the
keys it actually overrides — never a full copy of the defaults, or changing a
default would stop propagating to existing projects.

The setup panel is opened by the **gear icon in the WizardShell top bar**.

---

## 5. Data layout

```
3dgs-pipeline-app/
├── config.json                 # installation (paths, stubs)
├── defaults.json               # business defaults + capture presets
├── pipeline.db                 # SQLite: project registry only
├── backend/
│   ├── main.py                 # FastAPI app, routers, /static mount
│   ├── api/routes/             # projects, pipeline, settings, defaults, files
│   ├── api/websocket.py        # broadcast bus
│   ├── core/config.py          # config.json  (AppConfig singleton)
│   ├── core/defaults.py        # defaults.json (AppDefaults) + fps resolver
│   ├── core/probe.py           # ffprobe wrapper (pure)
│   ├── core/pipeline_runner.py # orchestrator, abort/pause
│   ├── core/steps/             # step_extract, step_rc, step_lfs, step_export, step_blender
│   └── core/curate/            # sharpness, scenes, overlap, select  (pure, no FastAPI)
├── frontend/src/…
└── projects/<slug>/            # ⚠ user data — never auto-deleted
    ├── input/                  # source video(s)          (FrameGate "sources")
    ├── frames/                 # extracted JPEG frames    (FrameGate "cache/frames")
    ├── analysis/               # curation JSON — see below
    ├── report/                 # report.json + report.md
    ├── rc_output/              # transforms.json, pointcloud.ply,
    │                          #   align.rscmd + alignment_check.json (§7.1)
    ├── lfs_output/
    └── export/
```

**Why per-frame data is JSON and not SQL:** a single project produces thousands of
frame records (score, verdict, displacement). They are written once per analysis
run and read as a block. They do not belong in the `settings_json` blob, and giving
them SQL tables would buy nothing but migrations.

```
projects/<slug>/analysis/
├── probe.json        # ffprobe output of the source video
├── extract.json      # what the extraction actually did: resolved working fps,
│                     #   source video path, mpdecimate flag, frame count
├── scores.json       # per frame: index, filename, sharpness, displacement_pct, sequence_id
├── selection.json    # kept[] / rejected[{frame, reason}] — regenerated on each analysis
└── overrides.json    # manual keep/drop from the UI — NEVER regenerated, always wins
```

`extract.json` is separate from `probe.json` on purpose: `probe.json` is the raw
ffprobe output of the source and nothing else, while the curation phase needs the
*resolved* working fps to map a cut timecode onto an extracted frame index — and
needs to know whether `mpdecimate` broke that mapping.

---

## 6. Step 2 — Extraction + curation (the merged FrameGate)

Step 2 owns the whole "clean image set" problem. It runs as one job with two
phases, and the analysis phase is independently re-runnable.

### 6.1 Extraction

- FFmpeg, working fps resolved by policy (§6.2), JPEG quality, optional max frames.
- **`mpdecimate` defaults to OFF.** It duplicates the overlap gate's job and, worse,
  it drops frames non-deterministically, breaking the frame-index ↔ timecode
  mapping that scene detection and the timeline depend on. The toggle stays
  available for users who skip curation entirely, with that warning in the UI.

### 6.2 Working fps policy

Three modes, in `defaults.json` under `extract`:

| Mode | Meaning |
|---|---|
| `auto` *(default)* | `fps = target_frame_count / duration_s`, clamped to the preset bounds, from ffprobe. This is the "evaluate the best value from the source" behaviour. |
| `ratio` | `fps = fps_ratio × source_fps`. Default ratio **0.2** — JB's habitual value, matching the RealityScan video-import default. On a 100 fps rush that is 20 img/s. |
| `absolute` | A literal fps typed by the user. |

`ratio` is the fallback whenever ffprobe fails or returns no duration.

**Capture presets** carry the target frame count and the overlap band together,
because they are two views of the same thing (how fast the camera travels):
`orbit_drone`, `handheld_walk`, `turntable`, `interior_scan`.

### 6.3 Analysis (curation)

Runs automatically after extraction, and can be re-run alone from a
"Re-analyse" button — thresholds are tuned iteratively and re-extracting frames
to change one number is unacceptable.

1. **Scenes** — PySceneDetect `AdaptiveDetector`. Each cut splits the footage into
   a *sequence*; RC should import sequences as separate image groups.
2. **Sharpness** — Tenengrad on greyscale, downscaled to ≤1080 px. Rejection is
   **relative**: below the rolling median of a 15-frame window by more than the
   sensitivity factor → `rejected:blur`. **Never ship an absolute threshold as a
   default** — it does not generalise across content.
3. **Overlap gate** — per sequence, median ORB feature displacement (% of frame
   width) against the last kept frame:
   - `< min_step` (2 %) → `rejected:redundant`
   - inside the band (2–12 %) → keep
   - `> band_max` → keep, flagged `warning:gap`
4. **Select** — merge verdicts into `selection.json`; `overrides.json` always wins.

> ~~The current placeholder in `api/routes/files.py` flags blur from the JPEG file
> size.~~ **Deleted 2026-08-20** when `curate/sharpness.py` landed. `/api/files/{id}/frames`
> now reads the verdicts from `analysis/selection.json` and reports `verdict: null`
> before the first analysis, rather than guessing.

### 6.4 Step 2 UI

One step, two panes: extraction settings + launch, then the frame gallery showing
per-frame verdicts, the sharpness timeline (recharts, already a dependency) with
cut markers, and per-frame manual override.

---

## 7. Dashboard metrics (implement exactly)

| Metric | Definition |
|---|---|
| Source info | ffprobe: container, codec, resolution, fps, duration, bitrate, HDR |
| Frames removed | Count + % of extracted, split by reason (`blur`, `redundant`, `manual`) |
| Frames blurred | Count of `rejected:blur` + sharpness timeline with cut markers |
| Overlap quality | % of consecutive kept pairs inside the band; median displacement; list of `warning:gap` positions |
| Global quality | Composite 0–100: (kept mean sharpness vs source mean) × 0.4 + (overlap-band ratio) × 0.4 + (1 − rupture density) × 0.2. **Always display the three sub-scores next to it** — the composite alone is marketing, the sub-scores are the truth |
| RC recommendations | Image count per sequence; **one project, one `-align`, one component** (§7.1); with ≥ 2 sequences raise the image-overlap preselection instead of trusting the sequential one; frames carry no EXIF → set camera/sensor prior manually; downscale if source > 4K; flag sequences < 30 images as alignment-risky; list `warning:gap` positions as likely alignment breaks |

### 7.1 Groups are not components

Three RC notions get conflated, and only one of them splits the output:

| RC notion | What it is | Splits the output? |
|---|---|---|
| **Project** (`.rcproj`) | The image database | Yes — separate projects never merge on their own |
| **Image / calibration group** | Images sharing lens intrinsics | **No** |
| **Component** | Result of alignment: cameras in one consistent frame | **Yes** — 2 components = 2 unrelated clouds, different scale and origin |

So "one group per sequence" was never about isolating sequences. Every frame of
every sequence goes into a single project and a single `-align`; what we want
out of it is exactly **one component**. And for a single source video, splitting
the *calibration* per sequence is actively worse — same physical camera, same
lens, so one group solves one focal length from all the observations instead of
N from fewer each.

What the sequence split buys on the RC side is the preselection mode: with one
sequence, sequential preselection is safe; with several, frame *k* and *k+1*
across a cut are unrelated, so the image overlap must go up (medium/high) for
the chunks to find each other.

**When alignment splits anyway**, in order of cost: keep the frames the overlap
gate rejected around the cuts (they are the bridge frames); raise max features
and image overlap; place ≥ 3 control points shared by both components and
re-align (GUI, no usable CLI verb); accept that two chunks which never see the
same surface cannot be merged by any setting — that one is a shoot-side answer.

`-selectMaximalComponent` keeps the largest component and **silently drops the
rest**: a 60/40 split trains LichtFeld on 60 % of the scene and just looks
"incomplete" for no visible reason. Step 3 therefore compares the frames fed in
against the cameras in the exported registration, writes
`rc_output/alignment_check.json` (counts, ratio, missing frames, per-sequence
breakdown) and **warns without failing** — a handful of unalignable frames must
not block the pipeline, and the call to re-align is the user's.

---

## 8. API

```
GET    /api/projects                   list
POST   /api/projects                   create
GET    /api/projects/{id}              one project
PATCH  /api/projects/{id}              partial update: deep-merged settings + curation overrides
POST   /api/pipeline/start             start a step
POST   /api/pipeline/control           pause / resume / abort
GET    /api/pipeline/status            running state
POST   /api/pipeline/analyze           re-run curation alone — never re-extracts
GET    /api/settings/                  config.json  (installation)
PUT    /api/settings/                  update config.json
GET    /api/defaults/                  defaults.json (business defaults)
PUT    /api/defaults/                  deep-merge update
POST   /api/defaults/reset             factory reset (optional ?section=)
GET    /api/defaults/presets           capture presets
GET    /api/files/{project}/frames     frame list + curation verdicts
GET    /api/files/{project}/analysis   scores.json + selection.json + overrides
GET    /api/files/{project}/probe      ffprobe metadata of the source video
GET    /api/files/{project}/alignment  RC coverage report (alignment_check.json)
WS     /ws/logs                        progress, logs, metrics
GET    /static/<slug>/...              project files (thumbnails, exports)
```

---

## 9. Optional module — auto-mask (SAM 2)

Deferred, not in scope. If revived: feature flag off by default, never imported at
module load, GPU-local only, and both the SAM 2 code AND the checkpoint licences
audited independently before enabling.

---

## 10. Licence audit table

Audit as if the tool could be distributed tomorrow. FFmpeg, RealityScan,
LichtFeld Studio and Blender are invoked as **subprocesses**, never linked.

| Dependency | Licence | Status |
|---|---|---|
| FastAPI / Uvicorn / Pydantic | MIT / BSD-3 | ✅ ok |
| SQLModel | MIT | ✅ ok |
| websockets, aiofiles, httpx, watchdog | BSD / MIT / Apache-2.0 | ✅ ok |
| OpenCV (`opencv-python`) | Apache-2.0 | ✅ ok — added for curation. **Not** the headless build: PySceneDetect depends on `opencv-python`, both wheels provide the same `cv2` package and cannot coexist. Same licence; the GUI symbols simply go unused (see `requirements.txt`) |
| NumPy | BSD-3 | ✅ ok — added for curation |
| PySceneDetect | BSD-3 | ✅ ok — added for curation |
| FFmpeg (system exe) | LGPL-2.1+ (GPL if built with x264) | ✅ ok as subprocess — re-audit before any distribution |
| RealityScan / LichtFeld Studio / Blender | proprietary / GPL, external | ✅ subprocess only, never bundled |
| React / Vite / Tailwind / shadcn/ui / Zustand / recharts | MIT | ✅ ok |
| SAM 2 + checkpoints, PyTorch | Apache-2.0 / BSD-3 | ⚠ only if the mask module is ever revived |

Any new dependency → add a row here in the same commit.

---

## 11. Conventions

- **Commits:** conventional commits (`feat:`, `fix:`, `chore:`, `docs:`…), English.
- **Code:** identifiers and docstrings in English. Comments in French welcome.
- **UI language:** currently English throughout. Keep it English and consistent
  until a deliberate switch — do not mix. *(Open question: the FrameGate spec
  called for a French UI; the existing app is English.)*
- **Python:** type hints everywhere, no FastAPI import inside `core/steps` or
  `core/curate`.
- **Frontend:** TypeScript strict, path alias `@/` → `src/`.
- **Typos in JB's prompts:** JB is dyslexic and types fast — interpret by intent,
  flag briefly only when a typo is genuinely ambiguous, never block on it.

---

## 12. Decisions log

| Date | Decision |
|---|---|
| 2026-08-20 | **FrameGate is merged into this app, not built separately.** Same stack, same tools; a separate repo would duplicate the project model, the WS bus and the settings UI. |
| 2026-08-20 | **WebSocket kept, SSE dropped.** The existing `/ws/logs` bus is wired through the store, LiveLog and ProgressBar; SSE would be a rewrite with no benefit for a local app. |
| 2026-08-20 | **SQLite for projects, JSON for frames.** Hybrid: the DB stays the project registry, per-frame curation data lives in `projects/<slug>/analysis/*.json`. |
| 2026-08-20 | **Existing directory names kept.** FrameGate's `data/<slug>/{sources,cache,output}` maps onto `projects/<slug>/{input,frames,export}`; only `analysis/` and `report/` are added. |
| 2026-08-20 | **`mpdecimate` defaults to OFF.** It duplicates the overlap gate and breaks frame-index ↔ timecode mapping. |
| 2026-08-20 | **Working fps has three modes**, `auto` by default, `ratio` 0.2 as fallback (JB shoots at 100 fps; 0.2 is the RealityScan video-import default). |
| 2026-08-20 | **Curation is merged into wizard step 2**, not a new step — avoids renumbering `_STEP_NAMES` / `_STEP_RUNNERS`, the `Step*` components and the `current_step` column of existing projects. |
| 2026-08-20 | **Analysis auto-runs after extraction and is separately re-runnable.** Threshold tuning must not force re-extraction. |
| 2026-08-20 | **No VPS deployment.** The app drives local GPU binaries; the FrameGate VPS track is dropped entirely. |
| 2026-08-20 | **Three settings layers with explicit precedence** (§4): `config.json` (installation), `defaults.json` (business defaults), `Project.settings_json` (per project). |
| 2026-08-20 | **`analysis/extract.json` added** to the four files of §5. The curation phase needs the resolved working fps to place a cut timecode on a frame index; `probe.json` stays the raw ffprobe output of the source. |
| 2026-08-20 | **Curation broadcasts under the step name `curate`, mapped to step 2** in the frontend store. Step 2 is one job with two phases, so the UI shows two progress bars without a seventh wizard step. |
| 2026-08-20 | **The overlap band comes from the capture preset by default** (`curate.overlap_from_preset`). §6.2 says the preset carries the target frame count *and* the band; before this the preset's band was dead data. The toggle pins the band by hand when needed. |
| 2026-08-20 | **The frames-only cut detector requires a relative *and* an absolute bar.** Measured on two real continuous shots, the relative bar alone (median + 6·MAD) invented 13 and 4 cuts where PySceneDetect on the source found none. Unlike sharpness, histogram correlation is normalised to [0,1], so an absolute floor is meaningful here. Errors are asymmetric: a missed cut is cheap, an invented one resets the overlap gate mid-shot. |
| 2026-08-20 | **RC image groups are not components (§7.1).** One project, one `-align`, one component — the sequence split drives the overlap gate and the preselection mode, never a partition of the reconstruction. Splitting the calibration per sequence would be strictly worse for a single-camera video. |
| 2026-08-20 | **Step 3 checks alignment coverage and warns, never fails.** `-selectMaximalComponent` drops the non-maximal components without a word; the check compares input frames against the exported registration and writes `rc_output/alignment_check.json`. Failing on a split would block the pipeline over a couple of genuinely unalignable frames — the decision to re-align is the user's. |
| 2026-08-20 | **The `.rscmd` is generated per run from the settings**, not shipped as a static file. `-mergeComponents` is absent from some RealityScan builds and an unknown verb makes RC exit non-zero, so the merge has to be switchable from the UI; `rc.extra_align_commands` is the escape hatch for verbs the app does not model. |
| 2026-08-20 | **The coverage check matches cameras by name, then by position.** `-exportRegistration` to a NeRF `transforms.json` does not keep the input filenames: RC writes undistorted copies renamed `00000.png`, `00001.png`… so a fully aligned project matched zero names and was reported as `0/300 · 0%`. When *no* name matches at all, the export was renamed rather than emptied — fall back to export order, which is the sorted input order. A renamed *and* short export reports the count only (`matched_by: "count"`), since which frames were dropped is genuinely unreadable from it. |
| 2026-08-20 | **`asyncio.CancelledError` is caught by name in the runner.** `/control abort` cancels the task outright, and `CancelledError` derives from `BaseException` — an `except Exception` never saw it, so an aborted step stayed "running" in the UI until a page reload. `StepStatus` gains `aborted`. |

Any new structural decision → add a row here in the same commit.

---

## 13. Backlog

Prioritised worklist lives in [TODO.md](TODO.md). This file is the spec; that
one is what comes next.
