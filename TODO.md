# TODO — 3DGS Pipeline App

Prioritised worklist. [CLAUDE.md](CLAUDE.md) is the spec; this file is what comes
next. Order = priority. Anything structural decided while doing one of these gets
a row in CLAUDE.md §12 in the same commit.

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
- **`frontend/src/api/client.ts` hardcodes `http://localhost:8000`**, which is
  the one hygiene rule §1 keeps from the dropped VPS track. `useDefaults` already
  uses relative `/api/...` URLs through the Vite proxy; the axios client should
  do the same.
