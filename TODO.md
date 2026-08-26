# TODO — 3DGS Pipeline App

Prioritised worklist. [CLAUDE.md](CLAUDE.md) is the spec; this file is what comes
next. Order = priority. Anything structural decided while doing one of these gets
a row in CLAUDE.md §12 in the same commit.

---

## P0 — Make the remaining progress bars real

Steps 2 and 4 report honestly now (CLAUDE.md §15 and the four 2026-08-23 rows in
§12). Three phases still have no number, in order of how long the user spends
staring at them.

**1. Step 3 — the RealityScan poller.** The route is measured and settled
(§15.3): `-writeProgress "<rc_output>/progress.txt" 1`, appended to the
generated `.rscmd` in `build_rscmd`, read by an `asyncio` task started next to
`spawn()` in `run_rc` and cancelled in the existing `finally` — the file is a
few tens of KB for a long run, so re-reading it whole each second is cheaper
than tracking an offset. A missing file must be a no-op, never a step failure.
Two things the format gives for free: a real ETA (4th column) and a task
ordinal, one per working verb of the script we generated ourselves, so the
phases are already identified without parsing anything.

Phase weights go in `defaults.json` under `rc.progress_weights`, seeded from the
653-image run measured on 2026-08-20 — `align 0.75, export_registration 0.18,
export_ply 0.02, postprocess 0.05` — and not hardcoded, because a 60-image
project has a different profile from a 653-image one. **Confirm first** that a
run with the COLMAP export enabled emits four tasks rather than three: the
experiment ran `-addFolder`, `-align`, `-exportSparsePointCloud` and got exactly
one task each, but neither `-exportRegistration` was in it.

**2. `rc_postprocess` reports nothing** while it rewrites a 142 MB ASCII PLY and
runs the coverage check. Bytes-read over file-size, pure Python, a handful of
lines.

**3. Curation phase 1 is where the time goes and the bar is flat.**
`scenes.detect_sequences` takes the `detect_from_video` branch, which hands the
whole source video to PySceneDetect inside one blocking `run_in_executor`; the
bar holds at 0.02 and then jumps to 0.25. `SceneManager.detect_scenes` takes a
per-frame callback, and `progress_cb` already exists in `scenes.py` — it is just
wired only into the `detect_from_frames` fallback, and `run_analysis` passes it
nowhere. While there: tick the curation chunks on a timer rather than every 24
frames, so the cadence does not depend on how expensive a frame happens to be.

---

## P6 — The mask route works, its step-3 UI does not (found 2026-08-26)

Both branches of the pipeline are verified end to end and neither needs a code
change on the backend: an imported PNG set with alpha reaches LichtFeld Studio
through `masks/` (§6.7, `fauteuille3d_test_v2`), and a source with no alpha
gets RealityScan's own masks through the COLMAP export (§7.5,
`publicsemple_truck`). What is wrong is what step 3 shows while and around it.

**1. The mask panel unmounts itself the moment it starts working.** The card is
gated on `masksEnabled && isDone` —
[Step3_RC.tsx:300](3dgs-pipeline-app/frontend/src/components/wizard/steps/Step3_RC.tsx#L300)
— and `isDone` is step 3's own status, which `run_mask_generation` sets to
`running` for the length of the run
([pipeline_runner.py:568](3dgs-pipeline-app/backend/core/pipeline_runner.py#L568),
by design: it is the wizard step the run belongs to). So the button, the report
and the `<ProgressBar step="masks">` on
[Step3_RC.tsx:321](3dgs-pipeline-app/frontend/src/components/wizard/steps/Step3_RC.tsx#L321)
all disappear on the click and come back when it is over — 40 s to several
minutes with nothing on screen, which is exactly the "bar that does not move"
§15 exists to forbid.

Nothing else is missing: `step_masks.py` already tails
`rc_output/masks_progress.txt` through `RCProgressTracker` over a plan built
from the mask script (§15.3's `20560` / `62` / `20576`), `websocket.py` carries
it, and both `stepNameToIndex` maps already route `masks` to step 3
([pipeline_store.ts:93](3dgs-pipeline-app/frontend/src/store/pipelineStore.ts#L93),
[ProgressBar.tsx:38](3dgs-pipeline-app/frontend/src/components/panels/ProgressBar.tsx#L38)).
The fix is the gate: render the card on `masksEnabled && (isDone || masking)`,
or on a status that distinguishes "aligning" from "masking". While there, check
the alignment bar above it —
[Step3_RC.tsx:190](3dgs-pipeline-app/frontend/src/components/wizard/steps/Step3_RC.tsx#L190)
renders `<ProgressBar step="rc">` on `isRunning || isDone`, so during a mask run
it shows the *previous* alignment frozen at 100 % under a `running` status. Two
runs share one step's status; the UI has to tell them apart or show only the
one that is live.

**2. The panel ignores the masks the project already has.** `rc.masks.enabled`
is an installation/project default, so the "Generate the masks" card is offered
identically to a project that has no masks and to one whose imported set kept
its alpha and already delivered `masks/` at step 2. In case A the run is not
merely redundant, it *overwrites* the artist's own cut-out with a mesh
silhouette — and the two are not the same picture (§6.7). Wanted:

- alpha kept (`extract.keep_alpha` true on a set with `has_alpha`) and the
  dataset already carries usable masks → do not offer the run as the normal
  path; state that the masks come from the source alpha, and keep the button
  only as an explicit, labelled fallback. It genuinely is one: alpha delivery
  refuses when RS's undistortion changed the geometry (§6.7's dimension guard),
  and that project has no masks at all until this run makes them.
- alpha dropped in step 2 (the "Drop it" answer,
  [Step2_Extract.tsx:295](3dgs-pipeline-app/frontend/src/components/wizard/steps/Step2_Extract.tsx#L295))
  or no alpha in the source at all → offer it exactly as today.

The panel cannot make that distinction from what it reads now: `MaskReport`
carries counts, sizes and a `state`, and **no provenance** — `ready` says the
same thing about masks extracted from a source alpha and masks rendered from a
mesh ([types/index.ts:254](3dgs-pipeline-app/frontend/src/types/index.ts#L254),
`/api/files/{id}/masks`). So the first move is a `source` field on the report —
`alpha` / `mesh` / `unknown`, written where the masks are delivered
(`rc_alpha.deliver_masks` vs `step_masks`) rather than guessed from the files —
and the step-3 copy keys on it. Same shape as §7.5's own lesson: an indicator
that answers a question about the *files* cannot answer a question about where
they came from.

---

## ~~P4 — Masks generated by RealityScan, from the region and the mesh~~ — DONE 2026-08-25

**Goal (met):** masks in RealityScan's *own* geometry, so LichtFeld Studio gets
a usable `masks/` folder on any project — not only on the imported PNG sets that
happen to carry alpha and happen to survive the undistortion. It is also the
only mask route for a project that starts from a video.

Shipped as **CLAUDE.md §7.5** — `POST /api/pipeline/masks`,
`run_mask_generation` in `pipeline_runner.py`, `core/steps/step_masks.py`,
`rc_alpha.fit_dataset_masks`, `GET /api/files/{id}/masks`, the "Generate the
masks" button under the region editor in step 3, and the `rc.masks` block in
the setup panel's RealityScan section. The full measurement is the §12 row of
2026-08-25; the task ids and the two failing verbs are in `docs/rs/README.md`.

**What the plan above got wrong, and it was the whole plan.**
`-exportMapsAndMask` answers **"Feature not implemented"** on RealityScan
2.2.0.119430 — with both arguments, a real preview mesh and every image
selected. The `ei*` keys were fine (`eiExportImageList` was honoured and
`imageList.txt` written); the exporter is simply not in this build. What works
is `colmapExportMasks`, an option of the COLMAP exporter step 3 already drives:
`-generateMaskFromMesh` puts a mask layer on every image, and re-running the
export with that option writes them into `<dataset>/masks/` **through the same
undistortion block and under the same basenames as `images/`**. So items 1 and
3 of "five things to settle" — the geometry and the naming — are not answered,
they are dissolved: 251 masks against 251 images, name for name, 973×543
against 973×543, measured. There is no `rs_masks/`, no delivery step and no
`rc_mask_params.py`.

Item 5, `-generateAIMasks`, was **not** measured against this route and stays
open — it needs no region and no mesh, and JB's turntable captures are what the
help says it is for. It would slot into `step_masks.build_masks_rscmd` as a
different middle: same load, same export, no `-calculate*Model`. Worth a run
before assuming the mesh route is the only one.

---

## P5 — The frontend still hardcodes `localhost:8000` (doc/code divergence)

CLAUDE.md §12's 2026-08-22 row says the frontend was made origin-relative —
"`client.ts` created its axios instance on `http://localhost:8010/api` and
`useWebSocket.ts` opened `ws://localhost:8010/ws/logs`, both are now
origin-relative". They are not, and the port in that row is wrong too:

- [frontend/src/api/client.ts:4](3dgs-pipeline-app/frontend/src/api/client.ts#L4) — `baseURL: 'http://localhost:8000/api'`
- [frontend/src/hooks/useWebSocket.ts:6](3dgs-pipeline-app/frontend/src/hooks/useWebSocket.ts#L6) — `const WS_URL = 'ws://localhost:8000/ws/logs'`

Both resolve against the *browser's* machine, so the app works on this
workstation and gives a blank wizard with a dead log bus from any other PC on the
LAN — the one hygiene rule §1 keeps from the dropped VPS track. `/api` and
`window.location.host` through the Vite proxy, as the row already describes; then
either the row is true or it is corrected. Check `server.host` in
`vite.config.ts` and the uvicorn bind at the same time, since the row claims
those too. (`Step5_Export.tsx:37`'s `http://localhost:4000` is a different thing
— a default for a *user-configured* external SuperSplat URL, not the app's own
origin.)

---


## ~~P1 — COLMAP export at the end of step 3~~ — DONE 2026-08-23

**Goal:** step 3 leaves `rc_output/` in the dataset layout LichtFeld Studio reads
best, so step 4 stops depending on the NeRF `transforms.json` path.

Target layout, next to the existing exports:

```
projects/<slug>/rc_output/
├── <slug>_COLMAP/          # ← the dataset, in a folder of its own
│   ├── images/             # the aligned frames, undistorted by RS
│   └── sparse/0/
│       ├── cameras.txt     # intrinsics — one camera per image, the whole point
│       ├── images.txt      # extrinsics, one entry per registered camera
│       └── points3D.txt    # the sparse cloud — LFS seeds the gaussians from it
├── transforms.json         # kept: the coverage check and the viewer read it
├── 00000.png…              # the NeRF export's own undistorted copies
├── pointcloud.ply
└── alignment_check.json
```

**The subfolder is not tidiness.** The layout above originally put `images/` and
`sparse/0/` directly in `rc_output/`, where the NeRF export's `00000.png…` have
the same basenames — and LFS refuses the whole dataset for it
(`COLMAP dataset contract violation: image '…' is ambiguous under '…'`). The
copy that trained correctly by hand was `rc_output/` with the top-level PNGs
deleted.

LFS is then invoked with `-d <rc_output>/<slug>_COLMAP` — step 4 resolves it
itself (`core/steps/colmap_dataset.py`) and falls back to `-d <rc_output>` with
a warning when there is no COLMAP dataset to be found.

**Route decided 2026-08-21: native RS export.** RealityScan 2.2 registers the
exporter in its own `calibration.xml` (format `{280B11A4-…}`,
`writer="RealityScan.Export.COLMAP"`), so no converter is needed — `build_rscmd()`
adds a second `-exportRegistration` pointing at an export-params XML generated
per run from `rc.colmap` (`core/steps/rc_export_params.py`). `directory_structure:
standard` is RS's own name for `images/` + `sparse/0/`, so the layout above comes
out of RS directly. See the two 2026-08-21 rows in CLAUDE.md §12.

**The trap, and where it actually was:** not the OpenGL→OpenCV flip — RS's
template does that itself — but the *world* frame. It hard-codes `Rx+90`, which
LFS's COLMAP loader passes through where its NeRF loader would have cancelled it.
`rc.colmap.scene_rotate_x_deg = 180` composes that back to `Rx-90` so the trained
splat stays the way up it is today.

**What a real RS run settled (riverbed_002-v2, 2026-08-23):** the
`<Configuration><entry key=…>` params file loads and the export runs —
`sparse/0/cameras.txt` carries 300 cameras for 300 images, against the single
top-level intrinsic the NeRF path gives all of them. That difference is the
whole bug: RS crops every undistorted image to its own size (frame 0
1523×1129 at fl 729.86, frame 1 1525×1136 at fl 728.25, hoisted median
1521×1136 at 721.30), so the NeRF route trains 300 cameras through intrinsics
that are wrong in a different direction each, and the reconstruction comes out
incomplete with exploded splat shells.

`transforms.json` is kept — the coverage check, `cameras.py` and the viewer all
read it, and it is the fallback when the COLMAP export fails.

**Still open, and no longer blocking:**

- **The enum tokens are still unverified, except `colmapFileType`, which is now
  known to be wrong.** Every file of the RealityScan 2.2 install was searched:
  `CDS_STANDARD`, `CFT_TXT` and `CME_EXT` are the only tokens of their families
  anywhere in the build, so `CDS_FLAT`, `CFT_BIN` and `CME_MASK_EXT` cannot be
  recovered from it — asking for `CFT_BIN` writes text, and the default is now
  `ascii` with a mismatch warning (decisions log, 2026-08-23). Saving the
  settings out of RS's export dialog once and running
  `rc_export_params.verify_against_saved_params()` against that file is still
  the one thing that would settle the rest.
- **`export_masks` and `directory_structure: flat` have never been exercised**,
  for the same reason: their tokens are guesses.

**Acceptance — met:**
- A real RS run produces `sparse/0/` with one camera per image. ✅
- Step 4 trains from the COLMAP dataset, and says so in the log; a missing
  dataset is a warning at step 3 *and* at step 4, never a silent fallback. ✅
- A re-alignment no longer leaves the previous run's frames in `rc_output/`. ✅

---

## ~~P2 — 3D preview of the sparse cloud at the end of step 3~~ — DONE 2026-08-20

Shipped wider than scoped: steps 3, 4 and 5 all render in-app. See CLAUDE.md
§7.3 and the decisions log.

What the investigation actually found:

- **The SuperSplat route was not merely untested, it could not work.**
  `config.json` sets `supersplat_url` to the *public* editor
  (`https://superspl.at/editor`), which cannot reach a `localhost` static file.
- **Neither output is loadable by a browser as it stands.** Measured on
  `coutryside_001`: `rc_output/pointcloud.ply` is 142 MB of ASCII (2.1 M points),
  `lfs_output/splat_9000.ply` is 1.24 GB (5 M gaussians, SH degree 3). So the
  decision was never "three.js or iframe" but "where does the file get made
  small" — and the answer is the backend (`core/ply.py`, ~1.7 s for the whole
  1.24 GB).
- **A step's output is not always the kind its number suggests** (the RS stub,
  removed 2026-08-22, wrote a gaussian PLY as `rc_output/pointcloud.ply`), so the
  renderer is chosen from the file's own properties, not from the step number.

Delivered: `core/ply.py`, `core/preview.py`, `core/cameras.py`, the three
`/api/files/{id}/{preview,cameras}` routes, `components/viewer/*`, a `viewer`
section in `defaults.json` and the setup panel. `PlyViewer.tsx` is deleted.

Still open, deliberately:

- **Live preview during training.** LFS writes `checkpoints/checkpoint.resume`
  (2 GB) rather than intermediate splats, so there is nothing to show mid-run
  without a `--config` save schedule (see the LFS row in the decisions log).
- **Colouring cameras by component.** `alignment_check.json` names the frames
  that never came back, and they have no pose — the viewer marks the amber
  *edges* of each hole instead. Actual per-component colouring needs RS to
  export more than the maximal component.

---

## ~~P3 — Project options: copy, reset, archive, info~~ — DONE 2026-08-21

Each tile of the Projects list carries a `⋮` menu: **Copy** (asks for a name,
duplicates files + wizard position), **Reset** (whole project or from any step —
`input/` is always kept), **Archive** (zips to `projects/_archives/<slug>.zip`,
the row stays in the list, disabled, until restored) and **Delete**. The tiles
now show the full path, the creation date and the last update. Spec: CLAUDE.md
§14; file operations in `backend/core/project_ops.py`.

Left open on purpose:

- **Copy / archive / restore are held requests, not polled jobs.** They run in a
  worker thread and stream per-file progress on `/ws/logs` behind a blocking
  modal (§14.2), so nothing looks hung — but the POST still stays open for the
  whole operation, and a browser reload mid-copy leaves the request orphaned and
  the modal gone (the files still land; the list needs a refresh). The preview
  build solved this with a POST that returns at once (§12, 2026-08-20); that is
  the pattern to copy if it ever bites.
- **No archive of the archive.** Restoring unpacks and deletes the zip; there is
  no "export this project somewhere else" verb, which is what a real backup would
  be.

---

## Known gaps found on 2026-08-20 (not scheduled, worth a decision)

- **RS precision / max features are not applied.** They live in `defaults.json`
  and in the step 3 Advanced panel, but `build_rscmd()` does not emit them — the
  app models no verb for RS alignment parameters. `rc.extra_align_commands` is
  the escape hatch meanwhile. Decide: find the real verb, or drop the two knobs
  from the UI rather than let them lie.
- **RS is fed the whole `frames/` directory**, curation verdicts included. The
  frames step 2 rejected as blurred or redundant still go into `-align`. Either
  that is deliberate (more frames = better chance of a single component, see
  §7.1) and should be said out loud in the UI, or step 3 should stage the kept
  frames into their own folder first.
- **`frontend/src/api/client.ts` hardcodes `http://localhost:8000`** — still
  open, and CLAUDE.md §12's 2026-08-22 row says otherwise. Moved up to **P5**
  above with the line references.
- **RealityScan's mask layers render at half the image resolution**, and none
  of the three global knobs reaches it: `mvsPreviewDownscaleFactor=1`,
  `txtImageDownscaleColor=1` and `-calculateHighModel` all produce the same
  half (CLAUDE.md §7.5). `rc_alpha.fit_dataset_masks` doubles them, which is a
  2×2 block per mask pixel — proportional, so a 4K source does not remove it,
  it only makes it a smaller fraction of the frame. **One lead is untested**:
  `ImageDepthMapDownscale` / `inpImageDepthMapDownscale` is a *per-input*
  setting in RS's Selected-inputs panel rather than a global reconstruction
  one, which would explain why every global key was a no-op. One run on
  `publicsemple_truck` answers it, and if it comes back full size the app
  simply stops resizing. Decided **not worth doing now** (2026-08-25): at the
  source sizes this pipeline actually shoots, half is not what the mask's
  quality is limited by — the mesh silhouette is.
