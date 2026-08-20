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

## P2 — 3D preview of the sparse cloud at the end of step 3

**Goal:** see `rc_output/pointcloud.ply` in the step 3 page once alignment is
done, so a bad alignment is visible before spending an hour in LFS training.

`PlyViewer` already exists (`components/panels/PlyViewer.tsx`) and is used by
step 5 — but it is an **iframe onto SuperSplat**, a gaussian-splat editor.
Whether it renders a plain RC sparse point cloud acceptably is untested, and
that is the first thing to check, because it decides the whole item:

- **If SuperSplat handles it** → this is ~10 lines: mount `<PlyViewer>` in
  `Step3_RC.tsx` with `plyUrl={/static/<slug>/rc_output/pointcloud.ply}` behind
  the same `isDone` guard as the coverage panel. Note that `PlyViewer` currently
  auto-resolves its URL from `exportFiles` (step 5 state) — pass the prop
  explicitly so step 3 never shows step 5's file.
- **If it does not** → an in-app viewer means three.js + `PLYLoader`, i.e. a real
  dependency. That needs a licence-table row (§10, three.js is MIT) and a
  justification, and it collides with the §1 non-goal *"no 3D viewer beyond the
  existing PLY preview"* — so it is JB's call, not a silent addition.

**Nice to have once it renders:** colour the cameras of a split component
differently, using `alignment_check.json`. That turns the coverage warning into
something you can actually see.

**Acceptance:** step 3 shows the cloud after a successful run; no viewer is
mounted before the file exists; step 5's viewer is unaffected.

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
