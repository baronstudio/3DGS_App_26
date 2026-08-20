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

**Two routes, decide by testing the installed RealityScan first:**

1. **Native RC export.** Check whether this build exposes a COLMAP registration
   export preset (`-exportRegistration <path> <exportParams.xml>`). If it does,
   this is one extra line in `build_rscmd()` and nothing else to maintain.
2. **Our own converter** (`backend/core/steps/colmap.py`, pure, no FastAPI), from
   `transforms.json` + `pointcloud.ply` → COLMAP **text** format. Text is enough:
   every loader reads it, and it stays diff-able.

**The trap either way:** conventions. `transforms.json` carries camera-to-world
matrices in the NeRF/OpenGL frame (Y up, Z back); COLMAP `images.txt` wants
world-to-camera as a quaternion + translation in the OpenCV frame (Y down, Z
forward). Getting this silently wrong produces a dataset that trains and looks
like mush. Write the axis flip and the inversion with a round-trip unit test
(`c2w → colmap → c2w` back to within 1e-6) before wiring it into the step.

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
