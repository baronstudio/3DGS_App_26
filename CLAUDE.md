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
- ~~No 3D viewer beyond the existing PLY preview.~~ **Superseded 2026-08-20**
  (§7.3): the "existing preview" was an iframe onto the *public* SuperSplat
  editor, which cannot reach a local file. Steps 3, 4 and 5 now render in-app.
  Still a non-goal: an *editor*. The viewer looks, it never writes.

---

## 2. Core principles (do not violate)

1. **No superfluous dependencies.** Every new dependency is justified and added to
   the licence audit table (§10) in the same commit.
2. ~~**Stub-driven development.**~~ **Dropped 2026-08-22** (§12): every step calls
   its real tool. There is no simulation layer, no `*_stub` flag and no fake
   output — a missing or misconfigured `.exe` fails the step with the path it
   looked for.
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
| App config | `config.json` — tool paths | Route `/api/settings` |
| App defaults | `defaults.json` — per-step business defaults | Route `/api/defaults` (§4) |
| Realtime | **WebSocket** `/ws/logs` (`backend/api/websocket.py`) | SSE from the FrameGate spec is dropped — the WS bus is already wired end to end |
| Video | FFmpeg + ffprobe (system exe, subprocess) | Path in `config.json` |
| Curation | OpenCV (Tenengrad, ORB) + NumPy + PySceneDetect | Added with the FrameGate merge |
| Alignment | RealityScan CLI — **RS** throughout | `step_rc.py` |
| Training | LichtFeld Studio CLI | `step_lfs.py` |
| Scene | Blender + `blender_splatforge.py` | `step_blender.py` |
| Frontend | React 18 + TS, Vite, Tailwind v4, shadcn/ui, Zustand, recharts | `frontend/` |
| Run | `start.bat` (Windows) / `start.sh` | Not a Makefile — this is a Windows-first app |

---

## 4. Settings model — three layers, explicit precedence

Three distinct things, three homes. Do not merge them.

| Layer | File / store | Contents | UI |
|---|---|---|---|
| **Installation** | `config.json` | `.exe` paths, URLs | Setup panel → "Tools" |
| **Defaults** | `defaults.json` | Business defaults per wizard step (fps policy, curation thresholds, RS precision, LFS iterations…) + capture presets + the 3D viewer (§7.3) | Setup panel → one section per step |
| **Per project** | `Project.settings_json` (SQLite) | What the user changed for THIS project | Wizard step "Advanced" panels |

**Precedence: per-project > defaults > code fallback.** A project stores only the
keys it actually overrides — never a full copy of the defaults, or changing a
default would stop propagating to existing projects.

The setup panel is opened by the **gear icon in the WizardShell top bar**.

---

## 5. Data layout

```
3dgs-pipeline-app/
├── config.json                 # installation (exe paths, URLs)
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
│   │                          #   + rc_postprocess (RS export → LFS, §7.2)
│   └── core/curate/            # sharpness, scenes, overlap, select  (pure, no FastAPI)
├── frontend/src/…
├── projects/_archives/         # ⚙ <slug>.zip of archived projects (§14)
└── projects/<slug>/            # ⚠ user data — never auto-deleted
    ├── input/                  # source video(s)          (FrameGate "sources")
    ├── frames/                 # extracted JPEG frames    (FrameGate "cache/frames")
    ├── analysis/               # curation JSON — see below
    ├── report/                 # report.json + report.md
    ├── rc_output/              # transforms.json, pointcloud.ply,
    │                          #   align.rscmd + alignment_check.json (§7.1)
    ├── lfs_output/
    ├── export/
    └── preview/                # ⚙ generated: browser-sized copies for the 3D
                               #   viewer (§7.3). Cache, safe to delete.
```

**Why per-frame data is JSON and not SQL:** a single project produces thousands of
frame records (score, verdict, displacement). They are written once per analysis
run and read as a block. They do not belong in the `settings_json` blob, and giving
them SQL tables would buy nothing but migrations.

```
projects/<slug>/analysis/
├── probe.json        # ffprobe output of the source video
├── extract.json      # what the extraction actually did: resolved working fps,
│                     #   source video path, mpdecimate flag, jpeg quality,
│                     #   output scale %, frame count
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

- FFmpeg, working fps resolved by policy (§6.2), JPEG quality, output scale,
  optional max frames.
- **JPEG quality and output scale are two different knobs.** `quality` is
  `-qscale:v`, the mjpeg quantiser: file weight and compression artefacts, never
  pixel dimensions. `scale_percent` is the resolution actually written to disk, a
  percentage of the source, applied *after* the fps gate so only the frames that
  survive it are resized. 100 % adds no `scale` clause at all, so the default
  extraction is unchanged. Both sides are truncated to an even number
  (`trunc(iw*f/2)*2`) — the mjpeg encoder writes yuvj420p and refuses an odd side.
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
   a *sequence*; RS should import sequences as separate image groups.
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
| RS recommendations | Image count per sequence; **one project, one `-align`, one component** (§7.1); with ≥ 2 sequences raise the image-overlap preselection instead of trusting the sequential one; frames carry no EXIF → set camera/sensor prior manually; downscale if source > 4K (`extract.scale_percent`, §6.1); flag sequences < 30 images as alignment-risky; list `warning:gap` positions as likely alignment breaks |

### 7.1 Groups are not components

Three RS notions get conflated, and only one of them splits the output:

| RS notion | What it is | Splits the output? |
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

What the sequence split buys on the RS side is the preselection mode: with one
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

### 7.2 What step 3 hands to step 4

RealityScan's two exporters do not agree with each other, and neither writes
quite what the LichtFeld Studio Blender/NeRF loader reads. Step 3 rewrites both
files in place after the alignment (`rc_postprocess.py`, gated on
`rc.normalise_for_lfs`):

| What RS writes | What LFS needs | Fix |
|---|---|---|
| `camera_model: SIMPLE_RADIAL`, `fl_x`/`cx`/`cy`/`w`/`h` **inside each frame** (its undistortion crops every image differently) | the model and the intrinsics at the **top level** | hoist the medians, name the model `PINHOLE` (`OPENCV` if any `k`/`p` is non-zero); the per-frame values stay |
| absolute `G:\…` image paths | anything resolvable | rewrite relative to `rc_output/` |
| `pointcloud.ply` in RS's own **Z-up** frame, `transforms.json` in NeRF **Y-up** | one frame | rotate the cloud `Rx+90`, `(x, y, z) -> (x, -z, y)`, stamped in the PLY header so a re-run is a no-op |

Without the first fix LFS logs `No camera intrinsics found, assuming
equirectangular`, then `Use --gut or --undistort to train on cameras with
non-pinhole model` — and exits 0. Without the third the sparse cloud lands 90°
off around X from the cameras that produced it: a scene standing upright next
to a flat camera path in the LFS viewer, and Gaussians initialised in the wrong
frame.


### 7.3 The 3D viewer (steps 3, 4 and 5)

Step 3 shows the sparse cloud, step 4 the trained splat, step 5 the exported
one. It is the only place several failures are visible at all: an alignment
that folded the camera path on itself, a component sitting at another scale, a
training that converged onto something other than the scene you shot.

**Nothing loads the step output directly.** Measured on a real project,
`rc_output/pointcloud.ply` is 142 MB of *ASCII* (2.1 M points) and
`lfs_output/splat_9000.ply` is **1.24 GB** — 5 M gaussians with the 45 SH
coefficients a preview never uses. `core/ply.py` streams the source and writes
a decimated binary copy into `projects/<slug>/preview/`, served by the existing
`/static` mount:

| Source kind | Preview | Record | Renderer |
|---|---|---|---|
| gaussians (`f_dc_*`, `opacity`, `scale_*`, `rot_*`) | `.splat` | 32 B — pos, exp(scale), SH-DC colour × sigmoid(opacity), quantised quaternion | `@mkkellogg/gaussian-splats-3d`, sorted and alpha-blended |
| plain cloud | `.pc3d` (ours) | 16 B — 3 float32 + rgba | `THREE.Points` |

Three consequences worth keeping:

- **The renderer is chosen from what the file *is*, not from which step asked.**
  A step's output is not guaranteed to be the kind its number suggests, so
  keying the viewer on the step number can pick the wrong renderer.
- **Decimation is a uniform spread, never a head slice.** A PLY is not
  shuffled; the first million points of an RS cloud are one corner of the scene.
  The level is a UI control (`viewer.preview_max_points`, default 1 M) and
  "Full" always loads the whole file — 5 M gaussians convert in ~1.7 s, so
  capping was never about the conversion cost, only about the download.
- **The preview is rebuilt when its source is rewritten**, tracked by mtime and
  size in a sidecar `.json`, never by age. `preview/` is a cache: deleting it
  costs one rebuild.

The camera overlay reads `rc_output/transforms.json` — camera-to-world in the
OpenGL frame, which is three.js's frame, so the basis goes in untouched.
Frustums are coloured per sequence and the path breaks at each cut. The frames
RS dropped cannot be drawn (they are absent from the export *because* they have
no pose); what is drawn instead is the amber edge of each hole, the bridge
frames of §7.1.

**Up is not the same way in the two frames the viewer loads.** §7.2's `Rx+90`
puts the sparse cloud back onto the cameras — and it does — but it sends RS's
+Z onto **-Y**, so everything in the RS frame is Y-*down* and three.js draws
step 3 upside down. LichtFeld Studio then applies its own `Rx+180`,
`(x, y, z) -> (x, -y, -z)`, when it reads the NeRF transforms, so the trained
splat comes out Y-up and needs nothing. The viewer therefore rotates **per
object, not per step** (`viewer/frame.ts`): RS-frame content — the `rc` preview
*and the camera overlay in all three steps* — is turned 180° around X for
display; LFS-frame content is not. It is a display transform, nothing on disk
moves. A "Flip up" toggle turns the whole view over for the scenes where RS's
+Z was never the true vertical to begin with.

## 8. API

```
GET    /api/projects                   list
POST   /api/projects                   create
GET    /api/projects/{id}              one project
PATCH  /api/projects/{id}              partial update: deep-merged settings + curation overrides
DELETE /api/projects/{id}              delete the row, the directory and the archive
POST   /api/projects/{id}/copy         duplicate under a new name (§14)
POST   /api/projects/{id}/reset        wipe steps {steps|null=all} — keeps input/
POST   /api/projects/{id}/archive      zip the directory away, keep the row disabled
POST   /api/projects/{id}/unarchive    unpack it back
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
GET    /api/files/{project}/alignment  RS coverage report (alignment_check.json)
GET    /api/files/{project}/preview    3D preview state (?source=rc|lfs|export&max_count=)
POST   /api/files/{project}/preview    build that preview — returns at once, poll the GET
GET    /api/files/{project}/cameras    camera poses of the last alignment, for the overlay
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
| three.js (`three`, `@types/three`) | MIT | ✅ ok — added for the 3D viewer (§7.3) |
| `@mkkellogg/gaussian-splats-3d` | MIT | ✅ ok — added for the 3D viewer; the sorted splat rasteriser (§7.3) |
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
| 2026-08-20 | **RS image groups are not components (§7.1).** One project, one `-align`, one component — the sequence split drives the overlap gate and the preselection mode, never a partition of the reconstruction. Splitting the calibration per sequence would be strictly worse for a single-camera video. |
| 2026-08-20 | **Step 3 checks alignment coverage and warns, never fails.** `-selectMaximalComponent` drops the non-maximal components without a word; the check compares input frames against the exported registration and writes `rc_output/alignment_check.json`. Failing on a split would block the pipeline over a couple of genuinely unalignable frames — the decision to re-align is the user's. |
| 2026-08-20 | **The `.rscmd` is generated per run from the settings**, not shipped as a static file. `-mergeComponents` is absent from some RealityScan builds and an unknown verb makes RS exit non-zero, so the merge has to be switchable from the UI; `rc.extra_align_commands` is the escape hatch for verbs the app does not model. |
| 2026-08-20 | **The coverage check matches cameras by name, then by position.** `-exportRegistration` to a NeRF `transforms.json` does not keep the input filenames: RS writes undistorted copies renamed `00000.png`, `00001.png`… so a fully aligned project matched zero names and was reported as `0/300 · 0%`. When *no* name matches at all, the export was renamed rather than emptied — fall back to export order, which is the sorted input order. A renamed *and* short export reports the count only (`matched_by: "count"`), since which frames were dropped is genuinely unreadable from it. |
| 2026-08-20 | **`asyncio.CancelledError` is caught by name in the runner.** `/control abort` cancels the task outright, and `CancelledError` derives from `BaseException` — an `except Exception` never saw it, so an aborted step stayed "running" in the UI until a page reload. `StepStatus` gains `aborted`. |
| 2026-08-20 | **Step 3 rewrites RS's export before step 4 reads it (§7.2).** RS's two exporters disagree with each other and with the LFS loader: `-exportRegistration` writes `camera_model: SIMPLE_RADIAL` with the intrinsics *inside each frame*, and `-exportSparsePointCloud` writes the cloud in RS's own Z-up frame while the registration is NeRF Y-up. LFS v0.5.3 then falls back to *equirectangular*, refuses to train — **and still exits 0**, so the step reported success over an empty `lfs_output/`. `rc_postprocess.py` hoists median PINHOLE intrinsics to the top level, relativises the image paths, and rotates the cloud by `Rx+90`, `(x, y, z) -> (x, -z, y)`. Switchable via `rc.normalise_for_lfs`. |
| 2026-08-20 | **A zero exit code from LichtFeld Studio is not success.** v0.5.3 catches its own training exceptions, logs `Training error: …` and exits 0. `step_lfs.py` now fails on that line *and* on an output directory with no `.ply`/`.splat` in it. The `cudaEventDestroy failed: driver shutting down` storm that follows every exit is CUDA teardown noise and is explicitly **not** treated as fatal — it is the visible symptom, never the cause. |
| 2026-08-20 | **The LFS CLI is read from the installed build, not remembered.** v0.5.3 renamed the strategies (`mcmc`, `mrnf`, `igs+`, default MRNF), prints progress as a `
`-redrawn bar rather than `iter n/N`, and colours everything with ANSI SGR codes. The runner splits on CR as well as LF, strips the escapes, and maps `[error]`/`[warn]` onto LiveLog levels. `lr`, `save_interval` and `render_mode` were **removed** from `LFSDefaults`, `defaults.json` and both settings panels: v0.5.3 has no CLI verb for any of them, so the controls round-tripped through `Project.settings_json` and were then silently dropped by the command builder. Upstream they live in `eval/*_optimization_params.json` (`means_lr`, `shs_lr`, `opacity_lr`, `scaling_lr`, `rotation_lr`, `save_steps` as a *list of steps*, not an interval) and are reachable only through `--config <file.json>`; `render_mode` is a rasteriser/viewer concern with no training meaning. Writing that config file is a feature, not a field — if it lands, it lands as its own panel. |
| 2026-08-20 | **Build artefacts and vendored binaries are untracked.** `node_modules/`, `.venv/`, `__pycache__/` and `tools/` were committed by the initial import — 27 393 tracked files, of which 27 096 were artefacts, so every commit carried Vite-cache and `.pyc` churn. They are now gitignored and removed from the index (files kept on disk). One exception stays tracked: the `tools/supersplat` gitlink. (`tools/test_assets/` was a second exception until the stubs were removed on 2026-08-22.) **A fresh clone therefore has no `tools/ffmpeg/` and no `tools/lichtfeld-studio-bin/`**: `setup.py` clones LichtFeld Studio from source and auto-detects FFmpeg on `PATH`, and the prebuilt binaries are re-downloaded by hand. That is the cost of not pushing ~1 GB of `.exe` to GitHub — where `slang-llvm.dll` (105 MB) would be rejected outright. |

| 2026-08-20 | **Abort kills the tool's process tree; Pause is gone from the exe-driven steps.** `/control abort` cancelled the asyncio task, but every exe step streams stdout from a thread-pool `readline()` and held its `Popen` in a local: the cancellation unwound the coroutine and marked the step aborted while `LichtFeld-Studio.exe` kept training on the GPU, unreferenced, with the reader thread stuck on a pipe that never closed. `core/proc.py` registers every child by project directory and `request_abort` `taskkill /F /T`s the tree — RS and LFS spawn workers, so killing the parent alone orphans the process that actually holds the GPU. Killing it is also what closes the pipe and unblocks the reader. A child killed that way raises `ProcessAborted`, handled like `AnalysisAborted` so the step is `aborted`, not `error`. **Pause was pure theatre** — the event is only awaited between steps and `/start` runs one step per call, so no running step ever observed it; none of FFmpeg, RealityScan or LichtFeld Studio has a pause verb anyway. The button is removed from step 4 rather than left lying; reviving it means suspending the child process (`NtSuspendProcess`) or threading the event into the curation loops, which is a feature, not a wiring fix. |
| 2026-08-20 | **The 3D viewer is in-app (three.js), and it never loads the step output (§7.3).** The SuperSplat route was dropped: `supersplat_url` points at the *public* editor, `https://superspl.at/editor`, which cannot reach a `localhost` static file — the iframe was not merely untested, it could not work. Against that, the §1 non-goal *"no 3D viewer beyond the existing PLY preview"* buys nothing, since the existing preview was the broken iframe. Two MIT dependencies, both in §10: `three` for the sparse cloud, `@mkkellogg/gaussian-splats-3d` for depth-sorted gaussians — a splat drawn as coloured points is a different picture, not a cheaper one. The size problem is solved in the backend, not the browser: 1.24 GB and 142 MB of ASCII are converted to a 32-byte `.splat` / 16-byte `PC3D` record and decimated by a uniform spread, cached under `projects/<slug>/preview/` and invalidated by source mtime. |
| 2026-08-20 | **The preview build is a POST that returns immediately, polled through the GET.** Converting five million gaussians is seconds, not milliseconds, and a request held open for the length of it is indistinguishable from a hung app. It is deliberately outside `pipeline_runner`: nothing it runs is an external tool, there is no process to kill, and cancelling it would only leave a `.part` file behind. |
| 2026-08-21 | **The up-axis fix lives in the viewer, per object, not in `rc_postprocess`.** §7.2's `Rx+90` maps RS's +Z onto -Y: cloud and cameras agree with each other, but the whole RS frame is Y-down and step 3 rendered upside down. Measured on `coutryside_001`, LFS applies `(x, y, z) -> (x, -y, -z)` to the NeRF frame — 95.7 % of the sparse cloud's occupied 2-unit cells land inside the trained splat's under that rotation, 10 % under identity, and no translation or scale — so the splat of steps 4-5 is already Y-up while the overlay built from `transforms.json` was flipped *relative to it*. Correcting `rc_postprocess` instead would only move the problem: LFS would then train Y-down and step 4 would be the broken one. So `viewer/frame.ts` rotates RS-frame objects by `Rx+180` at display time — the `rc` preview and the camera rig everywhere — and leaves the files alone. The "Flip up" toggle covers the alignments where RS's +Z is not the vertical. |
| 2026-08-21 | **The COLMAP export is RealityScan's own, driven by a generated export-params XML.** RS 2.2 registers the exporter in its `calibration.xml` — format `{280B11A4-F9A3-47D1-AE58-C0DEA33487D8}`, `writer="RealityScan.Export.COLMAP"` — with no `<body>`, because that template is compiled into the writer. So step 3 does not convert anything: `build_rscmd` adds a second `-exportRegistration` pointing at a params XML generated per run from `rc.colmap`, exactly as the `.rscmd` itself is. Three things this settles. **The dataset is written next to `transforms.json`, never instead of it** — the coverage check, `cameras.py` and the preview all read the NeRF export, and LFS prefers COLMAP anyway: `LoaderImpl::canLoad` probes `COLMAP dataset detected` *before* `Blender/NeRF dataset detected`. **`directory_structure: standard` is RS's own wording for `images/` + `sparse/0/`**, which is the layout the LFS loader looks for first, so nothing has to move 3 GB of PNGs. **Undistortion is not a preference**: RS refuses to write a COLMAP camera for its own `division` model and falls back to model id 13, which is not one of COLMAP's twelve — LFS answers `Invalid camera model ID 13 for image`. The real prize is per-image intrinsics: the NeRF loader reads `camera_model`/`fl_x`/`w`/`h` **once, at top level** (`Width/height not in transforms.json, reading from first image`), so §7.2's median hoist was telling 300 differently-cropped images they were the median image — measured on `coutryside_001`, frame 0 is 3793×2835 and frame 1 is 3785×2831. |
| 2026-08-21 | **The COLMAP scene is exported with `Rotate X = 180`, and that is what keeps the splat upright.** RS's COLMAP template hard-codes `(x, y, z) -> (x, -z, y)`, the same `Rx+90` as `rc_postprocess`, which puts the world Y-down. LFS's *NeRF* loader cancels that with its own `Rx+180` (§7.3); its *COLMAP* loader does not, because COLMAP is already the convention it wants — so an as-exported COLMAP dataset trains a splat 180° around X from today's, upside down in the viewer, in `export/` and in Blender. The dialog's `MvsExportRotationX` composes to `Rx-90` overall, `(x, y, z) -> (x, z, -y)`, and the order RS applies it in does not matter because rotations about one axis commute. Nothing downstream changes — `viewer/frame.ts` included. Exposed as `rc.colmap.scene_rotate_x_deg` rather than hardcoded, for the alignments where RS's +Z was never the vertical. |
| 2026-08-21 | **The project file operations are modal, and the dialog is mounted by the shell (§14.2).** Copy ran with nothing but a spinner on one tile: the user could start a step, switch project, or leave step 1 entirely — unmounting the list, and with it the only view of a running copy. None of these operations can be interrupted (there is no child process to kill, unlike a pipeline step), so the honest UI blocks. Progress travels on the existing WS bus under the step name `project`, which the store routes to the dialog rather than to `stepProgress`, and `copytree` was replaced by a file-by-file copy for the same reason: it is the only way to report anything before the end. Reporting every 20 files *and* every file over 8 MB, because a project of five 1 GB splats trips neither rule on its own. |
| 2026-08-21 | **`ui/button.tsx` is wrapped in `forwardRef`, because this app is React 18.** The file was the React 19 flavour of shadcn — a plain function component taking `ref` as a prop — and React 18.3 strips that ref instead. Every `<DropdownMenuTrigger asChild><Button/></DropdownMenuTrigger>` therefore gave Radix no anchor element, and an unanchored Popper never sets `isPositioned`: it parks its content at `translate(0, -200%)`, off the top of the page (`@radix-ui/react-popper`). The menu opened perfectly and was drawn where nobody could see it, so both the project options menu and the WizardShell project picker looked like dead buttons. Any shadcn component pasted from the v4 docs needs the same treatment until React is upgraded. |
| 2026-08-21 | **A project is copied, reset, archived or deleted from the list, and a reset never touches `input/` (§14).** Re-uploading the source video is the one cost a reset must not have — every other directory is derived and re-derivable. Resetting step N implies every later step, because their outputs were computed from the ones being deleted; `export/` therefore belongs to step 5, and step 6 owns only the two files it adds to it (`scene.blend`, `README_SPLATFORGE.txt`). All four operations refuse while a job is running for the project (`is_running`, exported from the pipeline routes) — the one-job-at-a-time rule is enforced there, so the answer to "is this directory being written to" lives there too. |
| 2026-08-21 | **Archiving zips the directory away and keeps the row, disabled.** The alternative — a "deleted" project that leaves 4 GB behind — is what the option exists to avoid, and a row that vanishes is indistinguishable from a delete. `projects/_archives/<slug>.zip` is inside `projects/` because it is user data (§3); the underscore cannot collide with a slug, which is `[a-z0-9_-]` stripped of leading underscores. Deflate at `compresslevel=1`: a project is mostly PLY — 142 MB of ASCII cloud, up to 1.24 GB of gaussians (§7.3) — where level 1 gets most of the ratio for a fraction of the time. The zip is written to `.part` and renamed, the directory is removed only after the archive is complete, and the zip is removed only after a restore has unpacked it: at no point is the project's only copy in flight. `preview/` is excluded from both the archive and the copy — it is a cache the viewer rebuilds. An archived project is refused by `/pipeline/start`, `/analyze`, copy and reset, and is filtered out of the two wizard project pickers. |
| 2026-08-21 | **Two projects no longer share a directory.** `create_project` slugified the name and used the result as-is, so a second project called "test" extracted its frames on top of the first one's. `_unique_slug` suffixes `-2`, `-3`… against both the DB and the disk; copy needs it anyway, and applying it to `create` costs one line. Existing rows keep their slugs. |
| 2026-08-21 | **The added columns are migrated with one ALTER each, not Alembic.** `SQLModel.metadata.create_all` only creates missing *tables*, so `archived_at` / `archive_path` would be absent from the existing `pipeline.db` and every query on them would fail with "no such column". `_add_missing_columns()` in `db/database.py` compares `PRAGMA table_info` against a declared list and adds what is missing — one user, one file, additive changes only. Anything a plain `ADD COLUMN` cannot express is the day this becomes a real migration tool. |
| 2026-08-21 | **The project tiles date from UTC explicitly.** The backend serialises naive `datetime.utcnow()` with no offset, and `new Date("…T12:00:00")` reads that as *local* time — on UTC+2 every project was stamped two hours in the future and read "just now" for an hour. The tiles stamp the `Z` back on before parsing, and show the full path, the creation date and the last update. |
| 2026-08-20 | **`.splat` and `.pc3d` are registered as `application/octet-stream`.** `StaticFiles` serves unknown extensions as `text/plain; charset=utf-8`, which invites anything in the path to treat a binary splat as text. |
| 2026-08-22 | **A preview file is never rewritten, and a cancelled download no longer keeps it open.** Rebuilding a preview failed with `[WinError 5] Accès refusé` on the `.part` → final rename: the previous file was still held open by the app itself. `StaticFiles` streams through `anyio.AsyncFile`, whose `aclose()` is a *thread* call starting with a cancellation checkpoint — so any aborted download (`PointCloudCanvas` aborts its fetch on every level change and unmount, React StrictMode's double-mount included) unwinds before the close and leaks the handle until the server exits. On Windows that handle blocks the rename, and would equally block deleting or resetting the project's `preview/`. Two changes, at both ends: `AsyncFile.aclose()` closes in place (`api/file_handles.py` — closing a file is a syscall, not blocking IO worth a worker thread, and inline it cannot be cancelled), and the preview name carries an 8-hex fingerprint of the source's mtime and size (`rc_1000000_3d67781a.pc3d`), so a new revision writes a new name instead of replacing one somebody may be reading. Older revisions of the same (source, level) are pruned best-effort after each build — a file the OS still pins costs 16 MB, not a failed build — and `ply._finalise` retries the rename twice before giving up with a sentence instead of a WinError. The fingerprinted URL also stops the browser serving the previous cloud from cache. |
| 2026-08-22 | **The frontend talks to its own origin, and only the dev server is exposed.** §1 keeps "no hardcoded `localhost` in the frontend API client" as hygiene even without a VPS — it was not held: `client.ts` created its axios instance on `http://localhost:8010/api` and `useWebSocket.ts` opened `ws://localhost:8010/ws/logs`, both of which resolve against the *browser's* machine, so opening the app from another PC on the LAN gave a blank wizard and a dead log bus. Both are now origin-relative (`/api`, and `window.location.host` for the socket), which routes them through the `/api`, `/static` and `/ws` proxies already declared in `vite.config.ts`. Vite gains `server.host: true`; **uvicorn stays on 127.0.0.1** — the proxy reaches it server-side, so port 5173 is the only thing on the network and the backend is not directly addressable. `staticUrl()` becomes a passthrough and stays, since `baseURL` is the one place to re-point at another origin. CORS in `main.py` is now moot (everything is same-origin) and is left as-is rather than widened. |
| 2026-08-22 | **Stub mode is removed, and core principle #2 with it.** The four `*_stub` flags, the four simulated runners (`run_extract_stub`, `run_rc_stub`, `run_lfs_stub`, `run_blender_stub`), `StubConfig`, `tools/test_assets/` and every piece of stub UI are gone. The dispatchers went too: `run_rc` / `run_lfs` / `run_extract` / `run_blender` *are* the real runners now, not a branch in front of them. What the stubs were for is over — the pipeline runs end to end against RealityScan 2.2, LichtFeld Studio v0.5.3 and Blender on this workstation, and what they cost was no longer theoretical: the RS stub wrote a *gaussian* PLY where the real RS writes a sparse cloud (§7.3), the LFS stub wrote an empty `output.splat` purely to exercise format detection, the FFmpeg stub emitted 1×1 JPEGs that the sharpness pass had to special-case, and §7.2's whole "the stub is exempt" caveat existed to explain why the simulated path skipped the normalisation the real one needs. Three of the four had also drifted from the tools they claimed to simulate (RealityCapture 1.5 banners, `cameras.bin`/`images.bin` COLMAP logs LFS v0.5.3 no longer prints). A simulation nobody trusts is a second, wrong implementation of every step. `SetupScreen` now reports which tool paths are configured rather than which are faked, and its Proceed gate is `rc_exe_path && lfs_exe_path` — previously any stub being on was enough to pass it. |
| 2026-08-22 | **A re-extraction starts from an empty frame set — it is a reset of step 2.** FFmpeg writes `frame_%04d.jpg` and overwrites in place, so re-extracting 300 frames over a previous 500 left 200 orphans on disk: the gallery kept showing them, and no `scores.json` entry described them. The curation JSON was stale the same way — `selection.json` and `scores.json` index frames whose content changed, and `overrides.json`, which §5 says is *never regenerated*, would have re-applied a manual keep/drop to a different picture. `run_extract` therefore calls `reset_steps(project_path, [2])` before the first frame is written: `frames/`, `analysis/` and `report/` go, `input/` never does — the same artefact list as the reset menu (§14.1), because it is the same operation. It runs **after** the source video is located, so a project with no video fails without costing the frames it already had. On the UI side step 2 empties the gallery and the curation stats on the click rather than on the first poll two seconds later. |
| 2026-08-22 | **Downscaling is an extraction setting, not an RS one (`extract.scale_percent`).** §7's "downscale if source > 4K" was a recommendation the app never acted on, and the only resolution control on screen was a "Quality" slider that changes nothing but JPEG compression — so the two got read as one. They are not: at `-qscale:v 5` a 4K frame is still 4K, and heavy compression is *worse* than a clean downscale for what comes next, since blocking artefacts read as edges to both RS's feature detector and the Tenengrad blur filter. The scale clause goes last in the filter chain (after `fps` and `mpdecimate`), which resizes only the frames that survive the gate. It changes nothing downstream: RS reads whatever resolution it is given, the curation pass already downscales to ≤1080 px to *measure* sharpness, and §7.2's per-image intrinsics come from RS's own undistortion either way. |

Any new structural decision → add a row here in the same commit.

---

## 13. Backlog

Prioritised worklist lives in [TODO.md](TODO.md). This file is the spec; that
one is what comes next.

---

## 14. Project lifecycle — copy, reset, archive, delete

Four options on each tile of the Projects list (`⋮` menu). All of them are
refused while that project has a job running, and all of them work on one slug.

**There is one project list, `components/projects/ProjectList.tsx`, and step 1
renders it** — embedded, without its Card chrome — in both of its modes: under
the import form when no project is selected, and at the bottom of the source
manager when one is. `ProjectList` was previously not rendered anywhere at all
(the step had its own read-only copy), which is the whole reason to keep a
single component: options added to one list are not options the user can find.

| Option | What it does | What it keeps |
|---|---|---|
| **Copy** | Asks for a name, duplicates the directory and the row — wizard position, step statuses and `settings_json` included | everything but `preview/`, which is a cache |
| **Reset** | Deletes the artefacts of a step and of every step after it, then rewinds `current_step` to just before it | **always `input/`** — the source video is never a casualty of a reset |
| **Archive** | Zips the directory into `projects/_archives/<slug>.zip`, removes the directory, keeps the row in the list, disabled | the zip, until it is restored or the project is deleted |
| **Delete** | Removes the row, the directory and the archive | nothing |

### 14.1 What a reset deletes

| Step | Directories | Files |
|---|---|---|
| 2 Extract | `frames/`, `analysis/`, `report/` | |
| 3 RS | `rc_output/` | |
| 4 LFS | `lfs_output/` | |
| 5 Export | `export/` | |
| 6 Blender | | `export/scene.blend`, `export/README_SPLATFORGE.txt` |

Step 1 is deliberately absent: it owns `input/`. Steps 5 and 6 share `export/` —
5 fills it, 6 adds the Blender scene to it — so resetting 5 necessarily takes 6
with it, which is exactly what "and everything after" means. `preview/` goes as
soon as any step from 3 on is reset: it is built from those outputs and would
otherwise show the previous run's cloud next to an empty directory.

The wizard's own state is rewound with the files: if the project being reset is
the one open in the wizard, the list re-hydrates it from the response instead of
leaving it on a step whose output no longer exists.

The file operations live in `backend/core/project_ops.py` — no FastAPI import,
so they are testable on a temp directory (§2.4).

### 14.2 The operations are modal

All four run behind a blocking dialog (`ProjectOperationDialog`), mounted by
`WizardShell` and driven from the store — not by the list, which unmounts the
moment the user changes step and used to take the only sign of progress with it.
Nothing dismisses the dialog: no Escape, no click-outside, no close button. It
opens when the request is sent and closes when it returns; on failure it stays
up holding the error until dismissed.

That is not decoration. A copy moves gigabytes file by file and **there is
nothing to abort it with** — no child process to kill, unlike a pipeline step
(§12, 2026-08-20) — so starting a step or another project operation on top of a
running one is a half-written directory, not a queue.

The bar is fed over the existing WS bus: the operations report under the step
name `project`, which the store routes to the dialog instead of to
`stepProgress` (it is not a wizard step). Copy, archive and restore run in a
worker thread and report every 20 files, plus every file over 8 MB — otherwise a
project of five 1 GB splats would sit at 0 % until it finished.
