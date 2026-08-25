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
| **Installation** | `config.json` | `.exe` paths, URLs, `ffmpeg_hwaccel` (§6.1) | Setup panel → "Tools" |
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
    │   └── <set>/             #   …or an imported image set (§6.7): the images
    │                          #   renamed `<set>_0001.png`, plus imageset.json
    ├── frames/                 # extracted JPEG frames    (FrameGate "cache/frames")
    ├── masks/                  # ⚙ the alpha channel of an imported PNG set,
    │                          #   extracted by step 2 as one greyscale PNG per
    │                          #   frame, same basename (§6.7). Never inside
    │                          #   frames/ — that folder goes to RealityScan.
    ├── analysis/               # curation JSON — see below
    ├── report/                 # report.json + report.md
    ├── rc_output/              # transforms.json, pointcloud.ply,
    │   │                      #   align.rscmd + alignment_check.json (§7.1)
    │   │                      #   + rc_progress.txt, RS's own bar (§15.3)
    │   └── <slug>_COLMAP/      # the COLMAP dataset step 4 trains on (§7.2):
    │                          #   images/ + sparse/0/. Its own folder because
    │                          #   the NeRF export writes the same basenames.
    ├── region/                 # ⚠ the Reconstruction Region (§7.4). **No reset
    │                          #   deletes it**: the box the user validated is
    │                          #   input to the mask route, not an artefact of
    │                          #   the alignment. region.json (app frame) +
    │                          #   region.rsbox (RS's frame) + region_auto.rsbox
    │                          #   (RS's own seed, rewritten every run).
    ├── lfs_output/
    ├── export/
    └── preview/                # ⚙ generated: browser-sized copies for the 3D
        └── sources/           #   viewer (§7.3), plus the poster frame and the
                               #   cached ffprobe of each input video (§6.5).
                               #   Cache, safe to delete.
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
├── scene_scores.json # FFmpeg `scdet` score per *source* frame, captured by the
│                     #   extraction on frames it was decoding anyway (§6.6).
│                     #   Scores, not cuts: the threshold is applied at analysis
│                     #   time so it stays tunable without re-extracting.
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
- **Hardware decoding is an installation setting** (`config.json` →
  `ffmpeg_hwaccel`, §4), not a per-project one: it describes the GPU in the
  machine, and no project wants a different one. `none` sends no flag; anything
  else becomes `-hwaccel <name>` on the input. It is deliberately *not* paired
  with `-hwaccel_output_format`, so the frames come back to system memory and
  the whole filter chain — `fps`, `mpdecimate`, `scale`, the scdet branch, the
  mjpeg encoder — is untouched. Measured on 20 s of 4K/100fps HEVC: **101.3 s →
  21.3 s** for the extraction. FFmpeg treats `-hwaccel` as a preference, so a
  source the GPU refuses decodes in software and still exits 0 — step 2 watches
  for that line and warns, because a silent fallback that costs 5× is not
  something to discover from the clock.
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

1. **Scenes** — from `analysis/scene_scores.json` when the extraction captured it
   (§6.6), otherwise PySceneDetect `AdaptiveDetector` on the source video, and
   the histogram fallback over the frames after that. Each cut splits the
   footage into a *sequence*; RS should import sequences as separate image
   groups. `curate.cut_source` pins one of the three.
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

### 6.5 The input sources panel

Step 2 says what it is about to read before it reads it. `/api/files/{id}/sources`
lists every file in `input/` with its ffprobe reading and a poster frame, and
badges the one video the extraction will actually consume — `find_extraction_source`
in `core/sources.py`, which `step_extract` calls too, so the badge cannot drift
from the file FFmpeg opens. Clicking a poster opens a mini player streaming the
file from `/static` (Starlette answers range requests, so seeking works without
copying anything anywhere).

It is not the same question as `/probe`, which reads `analysis/probe.json` — the
source of the *last* run, absent until there has been one. The fps policy (§6.2)
and the downscale (§6.1) are chosen against the cadence and the resolution of the
file about to be read, and until this panel neither was on the screen where the
choice is made. Step 2 now resolves its fps preview against the live probe and
falls back to `probe.json`, and states the estimate that follows from it: how
many frames this source, at this policy, will hand to curation.

Both the probe and the poster are cached under `preview/sources/`, named with the
same mtime+size fingerprint as the 3D previews (§12, 2026-08-22), so a re-uploaded
video gets a new name rather than a rename onto a file the browser is reading.

### 6.4 Step 2 UI

One step, two panes: extraction settings + launch, then the frame gallery showing
per-frame verdicts, the sharpness timeline (recharts, already a dependency) with
cut markers, and per-frame manual override.

### 6.6 Cut detection rides along with the extraction

Curation used to decode the source video a second time: FFmpeg read every frame
to extract, then PySceneDetect read every frame again to find the cuts. On a
52 s 4K/100fps rush that second decode measured **318 s**, and it is what §15.4
listed as the flat part of the curation bar.

The extraction now `split`s its decoded stream: one branch is the unchanged
`fps`/`mpdecimate`/`scale` chain, the other scales to 180 px and runs FFmpeg's
`scdet`, whose per-frame score `metadata=print` writes out. That branch costs
**~5 s per 20 s of 4K source** and removes the second decode entirely.

Three things this settles.

- **Scores are stored, not cuts.** `scdet=threshold=100` never fires; the
  thresholding happens at analysis time, so a threshold stays tunable from a
  re-analysis alone — which is the whole point of §6.3.
- **Both bars again, for §12's asymmetry.** A cut must be a local outlier
  (median + 8·MAD) *and* clear an absolute floor of 6. Measured here: two real
  hard cuts scored **14.59** and **13.14**, while the highest score anywhere
  across four genuinely continuous rushes was **2.51** (medians 0.009–0.066).
  FFmpeg's own `scdet` default is 10. The frame right after a cut echoes it
  (4.51, 2.49), which is what `min_scene_len` suppresses.
- **The scores are checked for truncation before they are trusted.**
  `metadata=print` is the one part of this that fails silently: FFmpeg rebuilds
  the filter graph when the input's resolution, pixel format or SAR changes
  mid-stream, and the rebuilt filter **reopens its file in write mode** —
  measured on a spliced source, a 720-frame video left 240 scores whose first
  entry sat at t=16 s. So the series is refused unless it starts at the top and
  reaches 90 % of the probed duration, and curation falls back to PySceneDetect,
  which decodes the video itself and cannot be fooled this way.

The metadata file is named **relative**, with `analysis/` given to FFmpeg as its
working directory: a filter option value is parsed for `:` and for the escape
character, so an absolute Windows path would have to be escaped into the
filtergraph, and a bare filename has neither character in it.

---

### 6.7 Image sets — when the frames already exist

Not every project starts from a video. A folder of stills, a zip from a phone
or a drone, a render sequence: the frames are already extracted, and step 2 has
nothing to pull out of anything. It **conforms** them instead — same output,
same `frames/`, same curation after it, so nothing downstream of step 2 knows
which branch ran.

**Three doors, because they are three different costs.** A **folder path** is
typed or pasted and read server-side: the app runs on the workstation that
holds the files (§1), so a 20 GB set is a local copy, never an upload. A
**zip** is one upload and one unpack — it is what a set that arrived from
somewhere else already looks like, and it can be dropped on step 1's create
screen to start a project. A **file selection**, including the browser's folder
picker, is the slow lane by construction and is kept because it is the only one
that works from another machine on the LAN.

**The images are renamed on the way in**, to `input/<set>/<set>_0001.png` —
zero-padded, contiguous, one extension. That is not tidiness: it is what makes
the set readable by FFmpeg's `image2` demuxer as a *single* input, so step 2
converts 900 images in one subprocess with a real `-progress` channel instead
of 900 subprocesses with none. `input/<set>/imageset.json` keeps the mapping
back to the original filenames, the origin (zip / folder / upload) and the
alpha answer. A set that is not a clean sequence — a folder dropped in by hand
with a gap in the numbering, or mixed formats — falls back to converting file
by file, with a line in the log saying so.

**Every image is a frame.** There is no cadence to resolve and no duration to
sample, so the fps policy (§6.2) does not apply and is not shown; `max_frames`
is the only gate, and it truncates the tail. `analysis/extract.json` records
`working_fps: null` and `input_video: null`, which is what sends curation to
the frames-only cut detector — the right one here, since there is no video to
run PySceneDetect on and no timecode to map onto. `probe.json` is written
`synthetic: true` with the nominal **30 img/s** the panel counts a duration
with; it is a unit, not a claim about the set.

**The conform copies rather than re-encodes when nothing has to change.** At
100 % scale, with the output format already matching, the frames are
hard-linked (falling back to a copy): re-encoding a JPEG at `-qscale:v 2` is
generation loss for no gain, and 900 20-megapixel PNGs is 18 GB that does not
need to exist twice. The link is safe against every operation the app performs
— a reset deletes `frames/`, which drops one link and leaves `input/`, the
directory §14 says a reset never touches.

**Alpha is for LichtFeld Studio, not for RealityScan.** RS has no concept of an
alpha channel on a *source* image; its mask layers are a different mechanism and
a different workflow, and it aligns on the full frame either way. (RS *can*
produce alpha image sets — from the Reconstruction Region combined with mesh
generation — and that is the route to masks in RS's own geometry. It is not
built.)

So when the set is PNG with a real alpha channel, step 2 asks — inline, next to
the estimate it changes, not in a modal answered on reflex — and keeping it
does two things, because they fail differently:

- the frames stay **RGBA PNG**, so the channel can ride *inside the images*
  through RS's COLMAP export and come out in RS's own undistorted geometry;
- the channel is **extracted into `projects/<slug>/masks/`**, one greyscale PNG
  per frame with the frame's basename — one `alphaextract` pass, and the layout
  LFS reads.

Never into `frames/`: a `<frame>.mask.png` beside its frame is RS's mask-layer
convention, and `-addFolder` would ingest it as one.

Step 3 then reports which copy survived (`rc_alpha.py`). If the export kept the
channel, nothing else happens — LFS reads it off the images ("Using alpha
channel as mask source"). If it did not, step 3 offers `masks/` to the dataset,
**but only after comparing the dimensions**: RS's undistortion crops every
image differently (§7.2), and a mask of the wrong geometry is worse than none —
it deletes real surface and keeps background, and LFS refuses it anyway (`Mask
'{}' is {}x{} but image '{}' is {}x{}`). That check is not a formality: an
alpha-carrying PNG set is very often a *render*, already pinhole, where the
undistortion is close to a no-op and the sizes do line up. Step 4 sends
`--mask-mode` only when the dataset actually carries masks.

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

**Step 4 trains on the COLMAP dataset**, `rc_output/<slug>_COLMAP/`, and step 3
is not finished until it has checked that the dataset is there
(`check_colmap_export`, written into the step result). What it buys is **one
intrinsic per image**: `sparse/0/cameras.txt` carries 300 cameras for 300
images, where the NeRF `transforms.json` carries one set of values at the top
level for all of them — and RS's undistortion crops every frame differently
(measured on `riverbed_002-v2`: frame 0 is 1523×1129 at fl 729.86, frame 1 is
1525×1136 at fl 728.25, against a hoisted median of 1521×1136 at 721.30). On
the NeRF path every camera therefore trains through intrinsics wrong by a few
pixels in a different direction, the optimiser cannot reconcile the rays, and
the result is an incomplete reconstruction with exploded splat shells. It is
not a resolution artefact — the spread is ~1.2 % of the image width, which
downscaling makes proportionally *worse*.

The NeRF export stays, and stays normalised: the coverage check (§7.1), the
camera overlay and the preview all read `transforms.json`, and it is what step 4
falls back to — with a warning naming the defect — when no COLMAP dataset is
found. So the table below is now about what the *viewer* and the *check* read,
and about the fallback, not about what normally trains.

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

### 7.4 The Reconstruction Region (step 3)

The region is the volume RealityScan reconstructs inside. It is the **input**
to the mask route of TODO P4 — a mesh is calculated inside it and each camera's
view of that mesh becomes that camera's mask — which is why it does not live in
`rc_output/`: a re-alignment resets step 3 (§12, 2026-08-23), and a box the
user placed by hand is the one thing in this feature that costs human
attention.

```
projects/<slug>/region/
├── region.rsbox        the validated box, in RealityScan's own Z-up frame
├── region.json         the same box in the app frame + provenance
└── region_auto.rsbox   what RS exported on its own — the seed, rewritten each run
```

Step 3 asks for a region and exports it (`rc.region`, three keys: `mode` —
`off` / `auto` / `density` — `scale`, `export`). The verbs go **after**
`-selectMaximalComponent`, so the box describes the component that actually
gets exported, and **before** the `-save`, so the saved `.rsproj` already
carries it. `-setReconstructionRegion*` and `-scaleReconstructionRegion` emit
no progress task at all; `-exportReconstructionRegion` emits one, id `21800`,
0.02 s (`docs/rs/README.md`).

**The `.rsbox` was read off RealityScan, not off a specification.** Its real
shape, and the two things a parser has to survive, are in `docs/rs/README.md`
with the sample files: the centre is nested in `<CentreEuclid>`, and
`yawPitchRoll` / `widthHeightDepth` come out as root *attributes* or as child
*elements* depending on how long RS's line got — both forms appeared in one run
of six exports.

**`yawPitchRoll` is not `(x, y, z)`.** Measured with
`-rotateReconstructionRegion`: field 1 rotates about **Y**, field 2 about
**X**, field 3 about **Z**, all stored negated, composing as
`R = Rz(-roll)·Ry(-yaw)·Rx(-pitch)`. `region.json` therefore stores
`euler_deg` as a plain `(rx, ry, rz)` triple **in the frame it names**, applied
`ZYX` — RS's own triple is kept under `rsbox` for the round-trip and nothing
else reads it.

**The frame is the whole trap, and it is proved rather than argued.**
`-exportReconstructionRegion` writes RS's native Z-up frame — the frame
`pointcloud.ply` was in *before* `rc_postprocess`. The app's canonical frame is
the NeRF one; `viewer/frame.ts`'s `Rx+180` and the "Flip up" toggle are display
only and live on the box's parent group, so nothing they do reaches a file.
Whether the cloud is in the NeRF frame at all depends on
`rc.normalise_for_lfs`, so it is **read from the PLY header marker**, never
assumed. And on every run step 3 counts the sparse points inside the exported
region, in both candidate frames:

```
[RS] Region: 150,804/153,307 sparse points inside (98.4 %), from region_auto.rsbox.
     Frame check (cloud is nerf) rc=35.6 %, nerf=98.4 %.
```

RS's automatic region contains most of its own cloud by construction, so one
frame scores ~0.9 and the other does not. The day those swap, something
upstream has moved.

**The editor is step 3's and only step 3's.** `SceneViewer` gains a
`withRegion` prop, passed from `Step3_RC.tsx` when `rc.region.mode !== "off"`,
and it draws nothing unless the preview turned out to be a point cloud —
`TransformControls` (already in `three@0.169`, so no §10 row), three modes,
with `dragging-changed` disabling `OrbitControls` for the length of a drag.
Every number the gizmo writes is also **typeable**: a gizmo alone cannot place
a box repeatably, and a box 2 cm out in Z is invisible on screen and fatal to
the mesh that comes next. The live "n/N points inside" is computed in the
browser from the loaded preview, with the same test the backend uses, and is
labelled as being over the decimated copy.

---

## 8. API

```
GET    /api/projects                   list
POST   /api/projects                   create
GET    /api/projects/{id}              one project
PATCH  /api/projects/{id}              partial update: deep-merged settings + curation overrides
DELETE /api/projects/{id}              delete the row, the directory and the archive
POST   /api/projects/{id}/copy         duplicate under a new name (§14)
GET    /api/projects/{id}/region       region.json, seeded from region_auto.rsbox (§7.4)
PUT    /api/projects/{id}/region       the validated box; writes region.json AND region.rsbox
DELETE /api/projects/{id}/region       back to RealityScan's automatic region
GET    /api/projects/{id}/image-sets   the imported image sets in input/ (§6.7)
POST   /api/projects/{id}/import-folder  read a folder on this machine, server-side
POST   /api/projects/{id}/import-zip     unpack a dropped zip of images
POST   /api/projects/{id}/import-images  a selection of image files (browser folder picker)
DELETE /api/projects/{id}/image-sets/{name}  remove one set from input/
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
GET    /api/version/                  app name, version (commit date) and commit id
GET    /api/files/{project}/frames     frame list + curation verdicts
GET    /api/files/{project}/analysis   scores.json + selection.json + overrides
GET    /api/files/{project}/sources    input/ listing: probe + poster frame per video
GET    /api/files/{project}/probe      ffprobe metadata of the *last extracted* source
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
| 2026-08-23 | **Step 4 trains on the COLMAP dataset, and it lives in a subfolder of its own.** Step 4 has never actually trained on COLMAP data: `step_lfs.py` passed `-d <project>/rc_output` and let LichtFeld Studio choose, and in every project that trained badly there was no COLMAP dataset there to choose — the export-params XML was the `<format>` shape RS refuses with `err:5617`, RS skipped the export **without failing the step**, nothing checked it, and LFS fell back to its Blender/NeRF loader in silence. Two changes settle it. The dataset is exported into `rc_output/<slug>_COLMAP/` rather than beside `transforms.json`, because the two exports collide: the NeRF one writes its undistorted `00000.png`… next to the json and the COLMAP one writes the same basenames under `images/`, which LFS refuses outright (`COLMAP dataset contract violation: image '…' is ambiguous under '…'`) — the hand-import that trained correctly was `rc_output/` with the top-level PNGs deleted. And step 4 resolves its own `-d` (`resolve_dataset`, `core/steps/colmap_dataset.py`), taking the COLMAP dataset when `sparse/0` holds a cameras/images pair and `images/` is not empty, falling back to the NeRF export **with a warning that names the defect** otherwise. Step 3 checks the same thing right after the export and warns there too, so a skipped export is visible at the step that skipped it. The lookup accepts any `*_COLMAP` in `rc_output/`, not only the current slug: a copied project keeps the directory the original wrote. Orientation is unchanged and was not touched — measured on an occupancy grid, the COLMAP export is `Rx180` from the NeRF-frame cloud (60.2 % cell overlap vs 3.7–5.4 % for the other rotations) and the GUI-trained COLMAP splat sits at identity against it (64.0 % vs 4.0–7.4 %), so with `scene_rotate_x_deg` at 180 both routes land in the same world frame and `viewer/frame.ts`, `export/` and Blender all stay as they are. |
| 2026-08-23 | **A re-alignment is a reset of step 3.** RealityScan writes into `rc_output/` without clearing it, so a 300-frame run over a previous one left 353 orphaned `00300.png`–`00652.png` behind — stale cameras for the coverage check, and duplicate basenames for the LFS loader now that a COLMAP dataset shares the directory. `run_rc` calls `reset_steps(project_path, [3])` before it writes the `.rscmd`, exactly as `run_extract` resets step 2 (2026-08-22) and for the same reason, and after the exe is located so a misconfigured path does not cost the alignment already on disk. |
| 2026-08-23 | **`colmapFileType` is asked for as ASCII, because binary cannot be asked for.** `CFT_BIN` was inferred and is wrong: RS wrote a text model every time. Every file of the RealityScan 2.2 install was searched for a `CFT_`/`CDS_`/`CME_` token and the only three that exist are `CFT_TXT`, `CDS_STANDARD` and `CME_EXT` — the three *defaults*, sitting consecutively in the string table right after their key names — so the real spelling of the counterparts is not recoverable from the build. Values are not validated when the params file is read (a token RS does not know is ignored, not refused), which is why this was invisible. The default becomes `ascii`, which is what RS writes either way, and `check_colmap_export` compares the model actually written against the one requested and warns on a mismatch — so the knob starts working the day the token turns up, instead of lying in the meantime. The cost of staying on text is `images.txt` at 73 MB and `points3D.txt` at 36 MB per run. |
| 2026-08-23 | **Max gaussians is exposed, because this build has a verb for it.** `--max-cap` is in `--help` on v0.5.3 and enforced in the trainer (`MRNF: count {} exceeds max_cap {}, pruning excess`), which is the bar the removed `lr` / `save_interval` / `render_mode` fields failed (2026-08-20). It matters in both directions: the GUI run on `riverbed_002-v2` finished at exactly **2 000 000** gaussians — the build's own ceiling, hit rather than converged to — and it is the first thing LFS suggests when it runs out of VRAM ("Try reducing max_cap, sh_degree, or image resolution"). `0` sends no flag and leaves the ceiling to the build, the same convention as `strategy: "default"`, so the number the app would otherwise freeze stays the build's to change. |
| 2026-08-23 | **The CR-split line reader is shared, and FFmpeg reports through `-progress`.** `_iter_output` was written for LichtFeld Studio's training bar (2026-08-20) and the same defect was sitting in step 2 and step 3 untouched: `readline()` splits on LF, and FFmpeg redraws `frame= … time=` with a bare CR on a line that never terminates, so the regex fired once, at exit. Three occurrences is where it becomes `proc.iter_lines()`. Step 2's numerator was broken independently — `progress = frame_count / max_frames if max_frames > 0 else None`, and `max_frames` is the optional cap, normally 0, so the value was `None` and the message was typed `log`. It now asks FFmpeg directly: `-progress pipe:1 -nostats` writes newline-delimited `key=value` blocks to stdout twice a second, and `out_time_us` divides into the `duration_s` that `probe.json` has held all along. `max_frames` stays as a second denominator when it is set, whichever is further along, because a 200-frame cap on a ten-minute source would otherwise crawl to 3 % and stop. Capped at 0.99 while running: the store reads 1.0 as "the step is done", and it is not until the frames are counted. Measured end to end on an 88 s 4K source — 0.002 to 0.990, smooth, over 372 s. |
| 2026-08-23 | **A message's type no longer decides whether its progress is used — and step 4's bar was never parsed to begin with.** `websocket.py` picks `msg_type` by priority and tests `data` before `progress`, so every LichtFeld Studio line, which carries both, went out as `metric`; the store's `metric` case only appended to `lfsMetrics`. The store now reads `progress` above the `switch`, for every type — the priority is right about what a message *is* and has no business deciding which of its fields may be read. That alone would still have moved nothing: measured against a real v0.5.3 headless run, the bar reads `Training […] 66% [00m:01s<00m:00s] 100/300 \| Loss: 0.1391 \| Splats: 281029`, and the iteration regex was anchored with `$` to a line that ends with the splat count, the fallback `iter n/N` form is not printed by this build, and the gaussian count is written `Splats:`, which nothing looked for. The bar's own percentage is not the training's — it read 33 / 66 / 100 % at "Initializing" / 100 / 200 — so the `N/M` pair is the only honest number on the line, mapped onto 5–95 % because a run loads its dataset for 10 s before iteration 1 and writes a checkpoint after the last. Its ETA is derived from that same broken percentage (`00m:00s` remaining at 100/300) and is **not** forwarded; the bar estimates its own. The metric gate is relaxed to match: PSNR exists only on the `[Evaluation at step N]` line an `--eval` run prints, so demanding iteration + loss + psnr + gaussians together meant no point ever qualified and the chart was empty for every run. Fields nobody reported stay `undefined` rather than being carried forward — recharts draws no line for a series that is never present, which is the truth about a run with no evaluation. |
| 2026-08-23 | **RealityScan reports through `-writeProgress <file> 1`; the log tail and `-printProgress` are both dead ends (§15.3).** `RealityScan.exe` is a GUI-subsystem binary, so the `readline()` loop in `run_rc` blocks until it exits and step 3 has never emitted anything but the final `1.0`. Measured on a real 110-image alignment: `-writeProgress "<file>" 1` writes live, about a line a second, across every task — while the same verb with the documented-looking `1000` created the file and wrote **0 bytes**, which is what made the feature look absent (the delta is in seconds, so 1000 means "never"). `-printProgress` does reach an anonymous pipe despite the missing console, but the CRT full-buffers it into 4 KB flushes and a whole alignment emits ~3 KB — one late update. And `%TEMP%\RealityScan.log` is frozen at the same byte count for the entire reconstruction, so tailing it would have covered every phase except the one that takes 1065 s. The format is `%d %.2f %.2lf %.2lf #%s` — task id, fraction, elapsed, **estimated remaining**, `started`/`progress`/`completed` — with one task per working verb of the `.rscmd`, in order, which is what `rc.progress_weights` will scale. The poller is not written yet; this row records the route so the measurement is not made twice. |
| 2026-08-24 | **Step 2 shows its input, and one function decides which video that is (§6.5).** The step chose the fps policy, the JPEG quality and the downscale for a video it never named: the settings summary listed the ffmpeg path and nothing about the file it would be pointed at, and `/probe` — the only source metadata on screen — reads `analysis/probe.json`, which describes the *previous* run and does not exist before the first one, i.e. it is empty exactly when these settings are being chosen. `/api/files/{id}/sources` probes what is on disk now, one entry per file in `input/`, each with a poster frame FFmpeg pulls a tenth of the way in (not frame 0 — that is the operator still reaching for the camera, or a fade-in), and the panel turns a click on the poster into a mini player over the step. The extraction source is *badged*, not restated: `run_extract` took `list(glob("*.mp4")) + list(glob("*.mov"))` and its `[0]`, and a UI repeating that rule is a second rule waiting to disagree with it — both sides now call `sources.find_extraction_source`, which is also what lets the panel warn that a second video in `input/` is never read. Probe and poster are cached under `preview/sources/` on the mtime+size fingerprint (2026-08-22), so the panel costs a directory listing after the first call, and a reset from step 3 on costs one ffmpeg call per video to rebuild. The player streams from `/static` rather than from a copy — Starlette answers range requests — and handles the decode failure explicitly, because the DJI rushes this app is built around are HEVC 10-bit and a browser that cannot decode one otherwise shows a black rectangle with no explanation. |
| 2026-08-23 | **A running step that says nothing for ten seconds gets stripes, not a number.** `ProgressBar` held whatever percentage arrived last, so the phases with no channel at all — PySceneDetect decoding the source video, RealityScan reconstructing, `rc_postprocess` rewriting 142 MB of ASCII PLY — were indistinguishable from a hung app, and its ETA was silent there too (samples are cleared below 5 %, which is exactly where those phases sit). After 10 s without a progress message a running step switches to indeterminate stripes and an elapsed count, keeping the last percentage beside them when there was one: "31 %, and nothing since" is more use than either a frozen bar or no number. The component's own step-name map was also missing `curate`, so step 2's second bar knew no status and never turned green. |
| 2026-08-24 | **A re-training is a reset of step 4** — the last of the four steps that wrote over its own previous run. LichtFeld Studio names its output after the iteration it stopped at (`splat_9000.ply`, `checkpoints/`, `metrics.csv`, `pointcloud.spz`) and writes into `lfs_output/` without clearing it, so a shorter second run left the previous splat beside the new one — and `run_lfs` returns `sorted(*.ply)[-1]`, which is not the file this run produced: after 9 000 iterations a 4 000-iteration re-run still reported `splat_9000.ply`, step 5 exported it, and the viewer showed it. `run_lfs` now calls `reset_steps(project_path, [4])` after the exe is located and before training, exactly as `run_rc` resets step 3 (2026-08-23) and `run_extract` step 2 (2026-08-22) — same function, same placement, same reason. It takes `preview/` with it (§14.1: the cache goes with any step from 3 on), so the viewer cannot show the previous training's splat over an empty directory. Each step clears **its own** folder only: resetting the later steps too is the reset menu's job, and a re-alignment that silently deleted a two-hour training would be a worse surprise than a stale one. |
| 2026-08-24 | **A re-export is a reset of step 5, and the four resets all run after their preconditions.** With step 4 clearing `lfs_output/`, `export/` was the last place a stale splat could survive a re-run: `run_export` copies every `*.ply`/`*.splat` under its own name, so a training that stopped at another iteration landed *beside* the previous one — `coutryside_001/export/` was holding a `splat_9000.ply` whose source no longer existed. It clears `export/` after the scan of `lfs_output/`, so an empty training does not cost the export already on disk. That takes step 6's `scene.blend` and `README_SPLATFORGE.txt` with it, which is what §14.1 already means by resetting 5: the two steps share the directory, and a Blender scene pointing at a splat that is gone is not worth keeping — the step says so in the log. The same audit moved step 2's reset, which sat *above* `resolve_ffmpeg_path`: that function raises when nothing is configured and there is no ffmpeg on PATH, so a bad tool path deleted the frames it was then unable to re-extract, exactly what its own comment claimed it avoided. The rule across all four: **locate the tool and the input first, delete second.** |
| 2026-08-24 | **Layer 3 of the settings model existed on paper only: the wizard panels now write to `Project.settings_json` on every change.** §4 has said since the merge that a project stores what the user changed for *that* project, and nothing ever wrote it — every row in `pipeline.db` held `{}`. The three Advanced panels seeded a `useState` from `defaults.json` (step 4 from a hardcoded copy of it, which had already drifted: `iterations` 30 000 against the file's own value) and threw it away on unmount, so a threshold tuned in step 2 was gone the moment the user looked at step 3, and the settings a project trained with were unreadable afterwards — they only ever existed in the `/pipeline/start` body. `useProjectSettings(projectId, section, defaults[section])` replaces the three copies: it reads the project's overrides, shows the defaults under them, and PATCHes back a **diff** — `deepDiff`, so a project stores only the keys it really overrides and changing a default keeps propagating, which sending the whole panel would have ended. There is no Save button because a panel that must be saved is a panel that gets lost; the 300 ms debounce that coalesces a slider drag is flushed on unmount, on a project switch (the patch is tagged with the id it was typed against) and on `beforeunload` through a `keepalive` fetch, and a failed PATCH puts its patch back rather than dropping it. On the backend `run_pipeline` and `run_analysis_only` overlay the stored layer *under* the request's, so a step started with `{}` — 5, 6, or any caller that is not that step's own panel — no longer silently falls back to the app defaults. Step 2's block travels nested under `extract` like `rc` and `lfs` rather than flat at the top level, which cost two lookups: `resolve_extract_settings` accepts both shapes, and `resolve_curate_settings` reads the capture preset from the nested block first — left alone it would have banded every project on the *default* preset the day step 2 stopped sending flat. |
| 2026-08-24 | **The alignment is saved as a `.rsproj`, before the exports.** RealityScan runs the whole `.rscmd` on an in-memory project and drops it on `-quit`, so an alignment that took an hour left nothing to reopen: re-inspecting it, placing control points on a split (§7.1 — GUI only) or re-exporting all meant aligning again. `build_rscmd` adds `-save "<rc_output>/<slug>.rsproj"` under `rc.save_project` (on by default, a switch in the setup panel's RealityScan section). It sits **after** `-align`/`-selectMaximalComponent` and **before** the two exports, because RS aborts the script on a verb it does not know — which is exactly what `-mergeComponents` is switchable for — and the alignment must survive an export that never runs. The file lives in `rc_output/`, so a re-alignment resets it with the rest of step 3 (2026-08-23). |
| 2026-08-24 | **The alignment settings are sent with `-set`, and until now none of them were.** `build_rscmd` wrote `-addFolder`, `-align`, the exports and nothing else, so `precision` and `max_features` — a radio and a slider present in *both* settings panels since the merge — reached RealityScan through no channel at all: every alignment ran on whatever the RS GUI had last been left on, and the two controls were decoration. RS's CLI takes application settings as `-set "key=value"`, and the keys are enumerated in the installed help (`Help/en-US/tutorials/setkeyvaluetable.htm`, "Alignment Settings") rather than guessed: `sfmFeatureDetectionQuality`, `sfmMaxFeaturesPerMpx`, `sfmMaxFeaturesPerImage`, `sfmImagesOverlap`. The four are emitted at the top of the `.rscmd`, before `-addFolder`, so `rc.extra_align_commands` can still override any of them. Three consequences. **Feature detection quality has two values in RS 2.2, not three** — `Normal` and `High`; the `Preview` the radio offered exists nowhere in RS, so `precision` becomes `feature_detection_quality` and an old project row carrying the dead key is dropped by `resolve_rc_settings` like any other unknown field. **Per-mpx is the cap that bites on a 4K frame**, the per-image number being a ceiling on top of it, which is why the panel that only exposed the second one could not explain a feature count; its app default is 30 000, this workstation's tuned GUI value, because sending RS's own 10 000 the day the key started being sent would have quietly detected a third of the features on every project. **And they are *application* settings, not project ones**: the CLI has no per-project scope for them, so a run leaves its values in the RS GUI's Alignment Settings panel — the app owns them now, which the setup panel says in as many words. Image overlap is exposed in both layers (§7.1 makes it the first thing to raise on a split), the per-mpx budget in the global one. |
| 2026-08-24 | **Step 3 has a progress bar, fed by `-writeProgress` and weighted by the script it just wrote.** The route was decided on 2026-08-23 and the poller left unwritten; writing it turned up two errors in the note that recorded it. **The task ids are stable and the ordinals are not** — four separate processes emitted the same ids (`65536` addFolder, `65537` align, `20576` exportRegistration, `20585` exportSparsePointCloud), while `-align` moved from task 2 of 3 to task 5 of 9 once the `-set` block and the `-save` were added; three of the "tasks" being counted were RS booting (`41061`, `41063`, `41064`, present when `-quit` is the whole script), and `-set` emits none. So `rc_progress.py` plans from the `.rscmd` `build_rscmd` generated and lets each id claim the next plan entry **of its own kind**, which keeps the bar honest when RS skips a verb without failing the script — the `err:5617` COLMAP export (2026-08-23) did exactly that. And the trailing `1` is a **heartbeat period, not a write interval**: the verb writes every change with no argument at all, and the `#timeout` lines it adds are what distinguishes a plateau from a hang, which the alignment needs — it sat at `0.55` for 20 s and `0.85` for 5 s of a 90 s run. The weights stay in `rc_progress.py` rather than becoming the `rc.progress_weights` the earlier note imagined: they measure the tool, like the 5–95 % mapping of the LFS bar, and nobody wants a slider for them. **`getStatus` was checked and rejected as the channel**: `-setInstanceName` + `RealityScan.exe -getStatus <name>` does answer, in 170–470 ms, without disturbing the run, and returns the same task, fraction and clocks the file already holds — but only for the task now running, so it can count nothing, and it costs a whole `RealityScan.exe` per poll. What it does prove is that the delegate family works headless, which makes `pauseInstance`/`unpauseInstance`/`abortInstance` real and §12's "no tool here has a pause verb" (2026-08-20) false for RealityScan. Not revived: that is a feature. |
| 2026-08-24 | **The version number is stamped by the sync, because git on the staging PC describes the wrong thing.** `/api/version/` reads `git log -1` in the app root — honest on a clone, a lie on the machine the code is *copied* to. `sync_staging.sh` delivers with `cp` over `git ls-files` and never touches `.git`, so staging reported **V2026.08.22** while running the files of the 24th: its HEAD sat on `4b500b4c` with eight commits of content on the disk beside it, and `git status` there listed 40 files as locally modified. A `fetch` + `reset --mixed` over there fixes one day and drifts again on the next push, so the sync now writes `3dgs-pipeline-app/.version_stamp.json` — commit, date, branch, `synced_at`, `synced_from` — and `version.py` prefers it. Two things keep that preference honest. The stamp carries a **`dirty` flag**: the script pushes the *working tree*, not the commit, so when any governed file differs from HEAD on the dev side it says the date is approximate and the top bar marks it `v2026.08.24*` — otherwise the stamp would replace a loud lie with a quiet one. And a stamp is **ignored once the clone moves past the commit it names** (`merge-base --is-ancestor`), so a real `git pull` on that PC takes precedence again; a commit the clone has never *seen* is not stale, which is the normal case there and was literally true on 2026-08-24 (`cat-file -e` failed on the commit the files came from). The file is gitignored: it describes one machine, never the repository. |
| 2026-08-25 | **Hardware decoding is one FFmpeg flag, and it is worth 5× on the extraction.** Step 2 had no `-hwaccel` anywhere and nothing in the app touched the GPU, on a workstation whose whole reason for being local is that it has one (§1). Measured on 20 s of 4K/100fps 10-bit HEVC: decode alone 92.9 s → 20.5 s, the real extraction shape 95.5 s → 17.9 s. The knob lives in `config.json`, not `defaults.json`: it describes the machine's GPU, and there is no reading of §4 in which one *project* wants a different decoder. It is deliberately **not** paired with `-hwaccel_output_format cuda` — without it FFmpeg downloads each frame back to system memory and the entire filter chain keeps working, where keeping frames on the GPU would mean `scale_cuda` + `hwdownload`, would break `mpdecimate` outright, and would save a PCIe copy that is not the cost. Default `none`, because a fresh clone is not promised an NVIDIA card. The one real trap is that `-hwaccel` is a *preference*: measured on a 4080×4080 h264 source, NVDEC answered `CUDA_ERROR_INVALID_VALUE`, FFmpeg decoded in software and **exited 0 with correct frames** — so `run_extract` matches that line, warns, and records `hwaccel_fell_back` in `extract.json`. A silent 5× regression is worse than a loud failure. |
| 2026-08-25 | **The cuts are found during the extraction, on frames FFmpeg is already decoding (§6.6).** Curation decoded the source a second time: PySceneDetect measured **318 s** on a 52 s 4K/100fps rush, which is exactly what §15.4 called the flat part of the bar. The extraction now `split`s its stream and runs `scdet` on a 180 px branch — **+5 s per 20 s of source** — and stores the per-frame *scores*, not the cuts, so the threshold stays tunable from a re-analysis alone (§6.3). End to end on the same 20 s clip, step 2 went from **220 s to 26 s** (extract 101.3 → 21.3 with CUDA, analyse 119.0 → 4.7). The detector keeps §12's 2026-08-20 doctrine — a cut must clear a relative bar *and* an absolute one — and the floor was measured, not guessed: two real hard cuts scored 14.59 and 13.14, the worst score across four continuous rushes was 2.51, so 6 sits >2× clear of both. **`metadata=print` has one silent failure and it is guarded**: FFmpeg reopens the file in write mode whenever it rebuilds the filter graph (a mid-stream resolution/SAR change), so a 720-frame spliced source left 240 scores starting at t=16 s — a series is refused unless it starts at the top and reaches 90 % of the probed duration. Three sources, `curate.cut_source`: `auto` prefers the captured scores and falls back on its own, `video` pins PySceneDetect (the reference this was measured against), `frames` pins the histogram fallback. PySceneDetect is **not** removed — it is the fallback, and on the one source where the two disagreed it was PySceneDetect that was wrong, inventing 5 cuts in a 5 s continuous turntable. |

| 2026-08-25 | **A project can start from images instead of a video, and step 2 conforms them rather than extracting (§6.7).** The pipeline assumed one video per project in three places — `find_extraction_source`, `run_extract`, and step 1's upload gate — so a folder of already-extracted frames had no way in at all. It now has three, chosen by cost: a **folder path read server-side** (the app runs on the machine that holds the files, §1 — pushing 20 GB through multipart to write it back onto the same disk is a copy with extra steps), a **zip**, and a **file selection**, which is the slow lane kept for another machine on the LAN. The images are **renamed at import** to `input/<set>/<set>_0001.png`, and that is load-bearing rather than cosmetic: a zero-padded contiguous sequence is what FFmpeg's `image2` demuxer reads as one input, so 900 images convert in **one** subprocess with a real `-progress` channel instead of 900 subprocesses with none — a set that is not a clean sequence falls back to file-by-file with a line in the log. At 100 % scale and a matching format the frames are **hard-linked, not re-encoded**: `-qscale:v 2` over a JPEG is generation loss for nothing, and 900 20-megapixel PNGs is 18 GB that need not exist twice; the link survives every operation the app performs, since a reset deletes `frames/` and leaves the `input/` copy §14 protects. **No fps policy applies** — every image is a frame, `max_frames` is the only gate, and `extract.json` records `working_fps: null` / `input_video: null`, which is precisely what routes curation to the frames-only cut detector (there is no video for PySceneDetect and no timecode to map). `probe.json` is written `synthetic: true` at a nominal 30 img/s, a unit for the panel and not a claim. **An image set outranks a video in the same `input/`**, badged and warned about in both steps, because a set is imported deliberately and later — the same treatment a second video already got. |
| 2026-08-25 | **The alpha of an imported PNG set is for LichtFeld Studio, and RealityScan is only in the way.** RS has no alpha concept for *source* images — its mask layers are a separate mechanism and a different workflow, and the way to get masks in RS's geometry is to have RS make them (Reconstruction Region + mesh generation), which is a feature of its own and is not built. So step 2 keeps the channel **twice, and never beside the frames**: the frames stay RGBA PNG so it can ride inside the images through the COLMAP export, and it is also extracted to `projects/<slug>/masks/` as one greyscale PNG per frame (one `alphaextract` pass, frame basenames, which is the layout LFS reads). Not as `<frame>.mask.png` sidecars: that *is* RS's mask-layer convention and `-addFolder` would ingest them, silently changing what the alignment runs on. The consumer's end was read off the binary rather than assumed — v0.5.3 has `--mask-mode=none|ignore|segment|segment_and_ignore|alpha_consistent`, `--invert-masks`, `--no-alpha-as-mask`, and names both channels it reads (`Using alpha channel as mask source ({}/{} cameras)`, `Mask mode enabled but no masks found in {}/masks/`). The hop in between is **measured at runtime, not predicted**: `rc_alpha.py` reads the PNG header of RS's export; if the channel survived, nothing else is needed, and if it did not, `masks/` is offered to the dataset **only when the dimensions still match**. That guard is the whole point — RS's undistortion crops every image differently (§7.2: 3793×2835 next to 3785×2831 from one uniform source), a mask of the wrong geometry deletes real surface while keeping background, and LFS refuses it outright (`Mask '{}' is {}x{} but image '{}' is {}x{}`). It is also not a formality in reverse: an alpha-carrying set is usually a render, already pinhole, where the undistortion is near-identity and the sizes do line up. A short export refuses too — position pairing means nothing once RS has dropped frames. `--mask-mode` is sent only when the dataset really carries masks, or v0.5.3 warns about a setting nobody chose. |
| 2026-08-25 | **`core/frames.py` is the one definition of "a frame", because a mask is a `.png` in the same directory.** `api/routes/files.py`, `step_analyze.py` and `step_rc.py` each kept their own `{".jpg", ".jpeg", ".png"}`, which was harmless while a frame was any image file and stopped being harmless the moment step 2 could write `<frame>.mask.png` beside `<frame>.png`: the gallery would have shown 600 pictures for 300 frames, curation would have scored the masks as frames, and the RS coverage check would have compared 600 inputs against 300 exported cameras and reported a 50 % alignment on a perfect one. Third occurrence of a rule is where it becomes a module — the same reason `proc.iter_lines()` exists (§15.1). |

| 2026-08-25 | **The region is placed in the app, stored in the NeRF frame, and written back to `.rsbox` in RealityScan's (§7.4).** Step 3 now asks RS for a region and exports it, and the step-3 viewer draws it as an editable box. Three things had to be measured before any of it could be written, and all three contradicted the proposal it came from. **The `.rsbox` shape**: SESSION 11 §1.3 guessed a flat element list; RS 2.2 nests the centre in `<CentreEuclid>` and writes `yawPitchRoll` / `widthHeightDepth` as root *attributes* or as child *elements* depending on how long the line got — both forms came out of one run of six exports, so neither is "the" shape. **The rotation**: `yawPitchRoll` is not `(x, y, z)`. `-rotateReconstructionRegion 30 0 0` writes `0 -30 -0`, `0 30 0` writes `-30 -0 -0`, `0 0 30` writes `0 -0 -30`, so field 1 turns about **Y**, field 2 about **X**, field 3 about **Z**, all negated; the composition order was solved by brute force over the six orderings against three two-axis runs and exactly one candidate fits them all, `R = Rz(-roll)·Ry(-yaw)·Rx(-pitch)`. `region.json` therefore stores a plain `(rx, ry, rz)` triple in the frame it names — keeping RS's own triple in a file stamped `"frame": "nerf"` would have been the frame error waiting to be made. **The frame**: `-exportReconstructionRegion` writes RS's native Z-up, i.e. the frame `pointcloud.ply` was in *before* `rc_postprocess`'s `Rx+90`, while the viewer's own `Rx+180` and its "Flip up" toggle are display only and now sit on the box's parent group where they cannot reach a file. Whether the cloud is normalised at all is **read from its header marker**, not assumed. And the chain is proved on every run rather than argued: measured on a real `fauteuil3d_test` run, RS's automatic region holds **98.4 %** of the sparse cloud in the NeRF frame against 35.6 % in RS's — one number, logged, that fails loudly the day something upstream moves. **`region/` is not a step artefact**: a re-alignment resets step 3 and a box the user placed by hand is input, so it sits beside `input/` in that respect — the only other directory a reset never touches. The acceptance test was RS itself: a box written by `rc_region.write_rsbox`, handed back through `-setReconstructionRegion` and re-exported, came out matching on every field to ≤ 5e-7 (`docs/rs/`). The dead "custom .rsbox" file input went with it — a browser file input yields a name, not a path, and no field of `RCDefaults` ever carried it. |

| 2026-08-25 | **`TransformControls.dispose()` is not called, because in three 0.169 it throws.** Every switch of the region gizmo's mode — and every unmount of the viewer, and every preview level change — died with `this.traverse is not a function` and took the React tree down to the step's error boundary. Upstream moved `TransformControls` from `Object3D` onto the new `Controls` base and left its `dispose()` calling `this.traverse(…)`, a method the class no longer has; the geometries it means to free hang off `getHelper()`, which *is* an `Object3D`. So the teardown calls `disconnect()` — the half that matters, since it is what removes the pointer listeners from the canvas — and walks the helper itself for the geometries and materials, which are safe to free because every one of them is built inside the `TransformControlsGizmo` constructor and shared with nothing. The gizmo is also **built once per box and re-pointed with `setMode`** rather than rebuilt per mode: switching mode is a click, and a teardown that is neither free nor safe should not be on that path. Same family as the `ui/button.tsx` forwardRef row (2026-08-21): a vendored component whose shape changed under a base class, silent until the one code path that touches it runs. |

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
| 2 Extract | `frames/`, `masks/`, `analysis/`, `report/` | |
| 3 RS | `rc_output/` | |
| 4 LFS | `lfs_output/` | |
| 5 Export | `export/` | |
| 6 Blender | | `export/scene.blend`, `export/README_SPLATFORGE.txt` |

`region/` is deliberately absent too, and it is the only directory outside
`input/` with that property (§7.4): the box in it is what the user validated,
and it is an input to the mask route rather than an output of the alignment. A
re-alignment overwrites the one derived file it holds — `region_auto.rsbox` —
and leaves the other two alone. A project copy takes the whole directory, like
everything else that is not `preview/`.

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

---

## 15. Progress reporting — what each tool can actually tell us

A bar that does not move is a bug report the user cannot file. Every step
reports from a channel that was **measured on this workstation**, not assumed,
and a phase with no channel says so instead of sitting on a number.

| Step | Channel | Denominator |
|---|---|---|
| 2 extract | FFmpeg `-progress pipe:1 -nostats` — `key=value` blocks on stdout, ~2/s | `out_time_us` against `probe.json`'s `duration_s`; `max_frames` too when capped, whichever is further along |
| 2 conform | FFmpeg `-progress pipe:1` over the image sequence — `frame=` | the image count, which is exact (§6.7) |
| 2 curate | `step_analyze._chunked`, every 24 frames | frame count — phase 1 is now near-instant when the extraction captured the scene scores (§6.6); it is still flat when it falls back to PySceneDetect |
| 3 RS | RealityScan `-writeProgress <file> 1`, tailed from `rc_output/rc_progress.txt` (§15.3) | the running task's fraction against the weighted plan of the `.rscmd` this run generated (`rc_progress.py`) |
| 4 LFS | the `Training […]` bar, redrawn with a bare CR | the `N/M` pair after the clock, mapped onto 5–95 % |

### 15.1 Three tools, one bug: the carriage return

FFmpeg, LichtFeld Studio and RealityScan all redraw a status line with a bare
CR, on a line that never terminates. `readline()` splits on LF only, so it hands
back the whole run as one line, at exit — which is exactly when the progress it
carries has stopped being useful. `proc.iter_lines()` splits on both and strips
the SGR escapes; every exe-driven step reads through it. It lives in `proc.py`
because that was the third place the same defect appeared.

### 15.2 A message's type does not decide whether its progress is used

`websocket.py` picks `msg_type` by priority and tests `data` before `progress`,
so an LFS line carrying both went out as `metric` — and the store's `metric`
case never touched `stepProgress`. The store now reads `progress` above the
`switch`, whatever the type. Reordering the priority would have been the wrong
fix: a message legitimately carries a metric *and* a position, and the type says
what it is mainly about, not which of its fields may be read.

### 15.3 RealityScan: the progress file, not the log and not stdout

Three candidate channels, measured on a real 110-image alignment:

| Channel | Result |
|---|---|
| `-writeProgress "<file>" 1` | **works.** Written live, ~1 line/s, from the first task to the last |
| `-writeProgress "<file>" 1000` | file created, **0 bytes** for the whole run — the delta argument is in seconds, so 1000 means "never" |
| `-printProgress 1000` | reaches the pipe, but the CRT full-buffers it: 4 KB flushes, and a whole alignment emits ~3 KB. One update, late |
| `%TEMP%\RealityScan.log` | **silent for the entire reconstruction** — frozen at the same byte count from the end of feature detection to the `Reconstruction completed` line |

So the log tail was never going to cover the phase that takes the time, and
`-printProgress` cannot be flushed from outside the process. The line format is
`%d %.2f %.2lf %.2lf #%s` — task id, fraction, elapsed s, **estimated remaining
s**, and `started` / `progress` / `completed`:

```
65537 0.00 0.01 142.40 #started
65537 0.41 12.52 18.38 #progress
65537 1.00 26.14 0.00  #completed
```

RS emits **one task per working verb** of the generated `.rscmd` — plus three
that are not verbs at all: `41061`, `41063`, `41064` are RS booting, and they
are present in a run whose entire script is `-quit`. `-set` emits nothing.
Measured on `fauteuil3d_test`, 251 frames, 106 s end to end:

| Task id | Verb | This run |
|---|---|---|
| `41061`, `41063`, `41064` | RS startup — not a phase | 0.00 s ×3 |
| — | `-set` | no task at all |
| `65536` (0x10000) | `-addFolder` | 0.19 s |
| `65537` (0x10001) | `-align` | **89.95 s** |
| `20533`, `20534` | `-selectMaximalComponent`, `-save` (not separable) | 0.10 / 0.59 s |
| `20576` (0x5060) | `-exportRegistration` — it undistorts and rewrites every image | 9.79 s |
| `20585` (0x5069) | `-exportSparsePointCloud` | 0.37 s |

**The id is the stable key and the ordinal is not** — the reverse of what this
section said until 2026-08-24. The ids repeated byte for byte across four
separate processes, `20585` matching the 110-image measurement above; the
ordinals moved, `-align` being task 2 of 3 there and task 5 of 9 here, because
the `-set` block and the `-save` landed in between and because the three startup
tasks were being counted as verbs. So `rc_progress.py` builds the expected list
from the script `build_rscmd` has just written and lets each incoming id claim
the next entry **of its own kind**. That resync is not decoration: a verb RS
refuses is skipped *without failing the script* — the `err:5617` COLMAP export
of §12 (2026-08-23) was exactly that — and a bar keyed on the ordinal alone
would then credit the alignment's weight to the wrong phase for the rest of the
run.

The weights live in `rc_progress.py`, not in `defaults.json` as an earlier
version of this section assumed: they are a measurement of the tool, like the
5–95 % mapping of the LichtFeld bar, and there is no reading of the app in which
the user wants a slider for them. They are relative and renormalised over
whatever verbs the script actually contains, so the second `-exportRegistration`
of a COLMAP run is weighted without a second table.

The second argument is a **heartbeat period, not a write interval**:
`-writeProgress <file>` with no argument at all still wrote all 104 lines of an
`-addFolder` run. `1` adds `#timeout` lines that repeat the last value when
nothing has changed, which is what lets the bar tell a plateau from a hang — the
alignment sat at `0.85` for 5 s and at `0.55` for 20 s. Why `1000` produced an
empty file is therefore *not* "the delta is 1000 seconds"; it is unexplained and
no longer worth explaining.

**`getStatus` is the same data, pulled, and it cannot build this bar.** The
delegate family (§8 of RS's help) reaches a running instance named with
`-setInstanceName`: `RealityScan.exe -getStatus RSPROBE` answers on its own
stdout, 170–470 ms per call, without disturbing the alignment —

```
[t+89.3 s] id:0x10001 progress:85.2% runtime:86.47sec endEstimation:15.46sec rev:1 lastError:0
[t+106  s] error: cannot find a running RealityScan instance      (exit 5)
```

— which is the same task, the same fraction and the same clocks the file was
carrying at that instant (`65537 0.85 87.49 15.66 #timeout`). It reports the
*current* task only, so it cannot count what completed, which is precisely what
an overall bar needs; and it costs a whole `RealityScan.exe` per poll. It is
worth keeping in mind for two things the file cannot do: `lastError:`, and a
liveness answer. **And it makes `pauseInstance` / `unpauseInstance` /
`abortInstance` real** — so §12's "none of FFmpeg, RealityScan or LichtFeld
Studio has a pause verb anyway" (2026-08-20) is false for RealityScan. Reviving
Pause for step 3 alone is a feature, not a wiring fix, and it is not done.

### 15.4 Where the bars are still flat

- ~~**Curation phase 1** decodes the whole source video inside one
  `run_in_executor`.~~ **Fixed 2026-08-25** (§6.6) for the normal path: the cuts
  now come from scores the extraction captured, so phase 1 is arithmetic over a
  list and the bar reaches 0.25 immediately. It is still flat on the two paths
  that decode — a forced `cut_source: "video"`, or the automatic fallback when
  the scores are missing or truncated — where `progress_cb` remains wired only
  into `detect_from_frames`.
- **`rc_postprocess`** rewrites a 142 MB ASCII PLY and runs the coverage check
  with no output at all.

Until a phase has a real number, `ProgressBar` is the honest fallback: a step
that has been `running` for 10 s without a progress message switches to
indeterminate stripes and an elapsed-time count, rather than holding a
percentage that stopped meaning anything.
