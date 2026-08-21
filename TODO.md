# TODO — 3DGS Pipeline App

Prioritised worklist. [CLAUDE.md](CLAUDE.md) is the spec; this file is what comes
next. Order = priority. Anything structural decided while doing one of these gets
a row in CLAUDE.md §12 in the same commit.

---

## P1 — COLMAP export at the end of step 3

**Goal:** step 3 leaves `rc_output/` in the dataset layout LichtFeld Studio reads
best, so step 4 stops depending on the NeRF `transforms.json` path.

Target layout, next to the existing exports:

```
projects/<slug>/rc_output/
├── images/                 # the aligned frames, as fed to RC
├── sparse/0/
│   ├── cameras.{bin|txt}   # intrinsics
│   ├── images.{bin|txt}    # extrinsics, one entry per registered camera
│   └── points3D.{bin|txt}  # the sparse cloud — LFS uses it to seed the gaussians
├── transforms.json         # kept: still what the stub writes and a useful fallback
├── pointcloud.ply
└── alignment_check.json
```

LFS is then invoked with `-d <rc_output>` unchanged — same flag, better dataset.

**Route decided 2026-08-21: native RC export.** RealityScan 2.2 registers the
exporter in its own `calibration.xml` (format `{280B11A4-…}`,
`writer="RealityScan.Export.COLMAP"`), so no converter is needed — `build_rscmd()`
adds a second `-exportRegistration` pointing at an export-params XML generated
per run from `rc.colmap` (`core/steps/rc_export_params.py`). `directory_structure:
standard` is RC's own name for `images/` + `sparse/0/`, so the layout above comes
out of RC directly. See the two 2026-08-21 rows in CLAUDE.md §12.

**The trap, and where it actually was:** not the OpenGL→OpenCV flip — RC's
template does that itself — but the *world* frame. It hard-codes `Rx+90`, which
LFS's COLMAP loader passes through where its NeRF loader would have cancelled it.
`rc.colmap.scene_rotate_x_deg = 180` composes that back to `Rx-90` so the trained
splat stays the way up it is today.

**Still open — this is what remains of P1:**

- **Nothing has been run against real RealityScan yet.** The parameter *names*
  are RC's (recovered from the executable's string table: `colmapDirStructure`,
  `colmapFileType`, `colmapPointFiltering`, `colmapExportMasks`,
  `colmapMaskExtension`, the `undist*` family, `MvsExportRotationX`), but only
  `CDS_STANDARD`, `CFT_TXT` and `CME_EXT` appear literally — `CDS_FLAT`,
  `CFT_BIN`, `CME_MASK_EXT`, `UFM_*` and `URM_*` are inferred, as is the
  `<format><parameter variable= value=>` wrapper. Save the settings out of RC's
  export dialog once and run `rc_export_params.verify_against_saved_params()`
  against it; that one file settles all of it.
- **Stub mode does not produce a `sparse/0/`.** The stub emulates RC's *result*,
  and RC is what writes the COLMAP files here, so there is nothing to reuse.
  Either the stub writes a small COLMAP set of its own, or step 4 keeps falling
  back to `transforms.json` when stubbed — decide once the real path is proven.
- **Step 4 does not say which dataset it trained on.** LFS switches from NeRF to
  COLMAP silently; until it is logged, a half-written `sparse/0/` is invisible.

**Acceptance:**
- Real RC run and stub run both produce `sparse/0/` and pass a re-import check.
- The converter is covered by the round-trip test above.
- Only frames present in the exported registration are written — the split
  reported by `alignment_check.json` must not reappear as broken camera entries.
- Step 4 trains from the COLMAP dataset with no change to its CLI flags.

**Open question for JB:** keep `transforms.json` as well (cheap, and the stub
already writes it), or drop it once COLMAP works? Default: keep both.

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
- **The RC *stub* writes a gaussian PLY as `rc_output/pointcloud.ply`**, so the
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
  *edges* of each hole instead. Actual per-component colouring needs RC to
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

- **RC precision / max features are not applied.** They live in `defaults.json`
  and in the step 3 Advanced panel, but `build_rscmd()` does not emit them — the
  app models no verb for RC alignment parameters. `rc.extra_align_commands` is
  the escape hatch meanwhile. Decide: find the real verb, or drop the two knobs
  from the UI rather than let them lie.
- **RC is fed the whole `frames/` directory**, curation verdicts included. The
  frames step 2 rejected as blurred or redundant still go into `-align`. Either
  that is deliberate (more frames = better chance of a single component, see
  §7.1) and should be said out loud in the UI, or step 3 should stage the kept
  frames into their own folder first.
- **`frontend/src/api/client.ts` hardcodes `http://localhost:8000`**, which is
  the one hygiene rule §1 keeps from the dropped VPS track. `useDefaults` already
  uses relative `/api/...` URLs through the Vite proxy; the axios client should
  do the same.
