# SESSION 11 — Reconstruction region → crop box → splat optimisation

## CONTEXT

BETA 2 runs end to end on the real tools (RealityScan 2.2, LichtFeld Studio
v0.5.3, Blender 5.1). What it does not do is control the **size of the final
splat**. A 30k-iteration run on a drone orbit lands at 2–4 M gaussians, most of
which describe the ground, the sky and the neighbours' roof — not the subject.

This session adds the missing chain, in three places:

```
[3] RS       set + export the reconstruction region      → rc_output/region.rsbox
                                                          → rc_output/crop_box.json
[4] LFS      seed training only inside that box           → pointcloud_cropped.ply
[5] Export   gaussian optimisation (LFS "Splat Simplify") → export/<stem>_<N>.ply
```

Everything below was checked against the **installed** binaries, not against
documentation. Where a verb does not exist, that is stated and worked around
rather than invented — the same rule that produced §7.2 of CLAUDE.md.

---

## 0. What the installed tools actually expose (verified)

### RealityScan 2.2 — CLI, from `Help/en-US/appbasics/allcommands.htm`

| Verb | Meaning |
|---|---|
| `-setReconstructionRegionAuto` | fit a region automatically |
| `-setReconstructionRegionByDensity` | fit the region to the **densest part of the sparse cloud** |
| `-setReconstructionRegion box.rsbox` | import a region |
| `-exportReconstructionRegion box.rsbox` | **export** a region |
| `-scaleReconstructionRegion sx sy sz origin\|center absolute\|factor` | resize |
| `-moveReconstructionRegion` / `-rotateReconstructionRegion` / `-offsetReconstructionRegion` | place |

Two consequences:

- RS exports **nothing** unless a region exists. A `-set…Region` verb must run
  before the export, and it must run **after `-align`** — `ByDensity` reads the
  sparse cloud.
- The file extension in RealityScan 2.2 is `.rsbox` (RealityCapture wrote
  `.rcbox`). Accept both on read.

### LichtFeld Studio v0.5.3 — CLI, from `LichtFeld-Studio.exe --help`

- **No crop-box flag.** Not in TRAINING PARAMETERS, not in DATASET OPTIONS.
- **No simplify verb.** `convert` has `--sh-degree`, `--lod-builder`,
  `--sog-iterations`, `-f/--format` — no target count, no opacity prune.
- What does exist and matters here:
  - `convert in.ply out.sog --sh-degree 0 -y` — real, working, and the single
    biggest size win available today (SH 3 → 0 removes 45 of 59 floats per
    gaussian).
  - `--config <file.json>`, whose key set is not readable from the binary — do
    not build on it this session.

### LichtFeld Studio v0.5.3 — what it does internally

From the shipped Python plugins (`bin/lfs_plugins/`) and the exe's own strings:

- The trainer *is* crop-aware: `lfs::training::loadTrainingDataIntoScene` logs
  `CropBox filtering: {} -> {} points` and `CropBox filtered out all points`.
  The box comes from a **scene node**, which only exists in a GUI session — so
  it is unreachable from `--headless --train`.
- The Blender/NeRF loader reads **`ply_file_path`** out of `transforms.json`
  and falls back to `pointcloud.ply` (`src/io/loaders/blender_loader.cpp`
  strings). **This is the hook the crop rides on** — §2 below.
- Splat Simplify is a Python-API call, not a CLI one
  (`bin/lfs_plugins/rendering_panel.py`, `_start_simplify`):

  ```python
  lf.simplify_splats(source_name,
                     ratio=target_count / original_count,
                     lod_base=...,                    # clamp [0.1, 10.0], default 2.0
                     opacity_prune_threshold=...)     # clamp [0.0, 1.0], default 0.10
  # progress: lf.is_splat_simplify_active() / get_splat_simplify_progress()
  #           / get_splat_simplify_stage() / get_splat_simplify_error()
  # cancel:   lf.cancel_splat_simplify()
  ```

  The same file gives the GUI's defaults and clamps, which the UI must
  reproduce exactly (§4.3): target ratio 0.5, target ∈ [1, original], output
  name `<source>_<target>`.

  JB reports this tool is **bugged in 0.5.3, fixed in the next build**. So the
  engine is modelled, probed for, and *not* trusted this session.

---

## 1. Step 3 — set and export the reconstruction region

### 1.1 New `rc` defaults (`backend/core/defaults.py`, `defaults.json`)

```python
class RCDefaults(BaseModel):
    ...
    # Which -set…Region verb runs before the export. RS exports nothing unless
    # a region exists, and the region must be set after -align: ByDensity reads
    # the sparse cloud. "off" skips the whole region block.
    region_mode: Literal["off", "auto", "density"] = "density"
    # -scaleReconstructionRegion sx sy sz center factor. The density fit hugs
    # the subject; a little air around it is usually what you want.
    region_scale: list[float] = Field(default_factory=lambda: [1.1, 1.1, 1.1])
    export_region: bool = True
```

### 1.2 `build_rscmd()` — new block, in this order

```
-addFolder <frames>
<extra_align_commands>
-align
[-mergeComponents]
[-selectMaximalComponent]
[-setReconstructionRegionByDensity | -setReconstructionRegionAuto]     ← new
[-scaleReconstructionRegion sx sy sz center factor]                    ← new
[-exportReconstructionRegion "<rc_output>/region.rsbox"]               ← new
-exportRegistration "<rc_output>/transforms.json"
-exportSparsePointCloud "<rc_output>/pointcloud.ply"
-quit
```

The region verbs sit **after** the component selection so the box describes the
component that actually gets exported, and **before** the exports so a failure
there is visible in the same run.

### 1.3 New pure module `backend/core/steps/rc_region.py`

No FastAPI, no broadcast — returns reports the step broadcasts (core principle #4).

```python
parse_rsbox(path: Path) -> OrientedBox | None
    # XML. Tolerant by design, RS's writer has changed shape between versions:
    #   <centre> | <center>          3 floats
    #   <widthHeightDepth>           3 floats
    #   <yawPitchRoll>               3 floats, DEGREES
    #   <residual R=… t=… s=…>       optional rigid+scale correction, applied if present
    # Anything missing → None, and the caller falls back (§1.5).

corners(box) -> list[[x, y, z]]        # 8, in RS's frame

to_lfs_frame(points) -> list[...]      # (x, y, z) -> (x, -z, y)

box_from_pointcloud(ply, percentile=1.0) -> AABB
    # fallback, and the sanity reference. Percentile, not min/max: one stray
    # point 400 m away otherwise defines the whole box. LFS's own
    # crop_box.fit defaults to percentile bounds for the same reason.

write_crop_box(rc_output, box, source, stats) -> dict
```

**The trap that must not be got wrong.** `-exportSparsePointCloud` writes the
cloud in RS's own Z-up frame and `-exportRegistration` writes the cameras in the
NeRF Y-up frame; `rc_postprocess.align_pointcloud_to_cameras` already rotates
the cloud by `Rx+90`, `(x, y, z) -> (x, -z, y)` to reconcile them (CLAUDE.md
§7.2). **The region is exported in the same Z-up frame as the cloud and needs
the exact same rotation.** Skip it and the crop box sits 90° off around X — it
will not error, it will quietly delete the scene and keep the sky.

Rotate the **8 corners**, not min/max: the region is oriented (yaw/pitch/roll),
so its axis-aligned bounds in the LFS frame are the bounds of the rotated
corners.

### 1.4 `rc_output/crop_box.json`

```json
{
  "source": "rsbox",
  "frame": "lfs",
  "usable": true,
  "min": [-2.41, -0.12, -3.05],
  "max": [ 2.38,  3.44,  2.97],
  "center": [-0.015, 1.66, -0.04],
  "size": [4.79, 3.56, 6.02],
  "corners": [[-2.41, -0.12, -3.05], "…8 in total"],
  "rc_frame": { "centre": [], "widthHeightDepth": [], "yawPitchRoll": [] },
  "points_inside": 214883,
  "points_total": 286104,
  "coverage": 0.751
}
```

`source` ∈ `rsbox` | `pointcloud_percentile` | `manual`. It lives next to
`alignment_check.json` and follows the same rule: **warn, never fail**.

### 1.5 Guard rails (mandatory — this is the failure mode of the whole feature)

The step computes `points_inside / points_total` against the rotated cloud and:

- `coverage < 0.05` or any `size <= 0` → `"usable": false`, WARNING, and step 4
  trains **uncropped**. A box that keeps nothing is a bug, not an instruction.
- No `.rsbox` / unparseable / `region_mode == "off"` → fall back to
  `box_from_pointcloud(percentile=1.0)`, `source: "pointcloud_percentile"`,
  INFO not WARNING. That fallback is a genuinely useful box.
- Log the coverage on every run: `[RS] Crop box: 214 883/286 104 sparse points
  inside (75.1%), from region.rsbox.`

### 1.6 Stub

`run_rc_stub` writes a plausible `region.rsbox` and a `crop_box.json` derived
from `sample.ply` percentiles, so step 4's crop path is exercisable with no GPU
(core principle #2). The stub emulates RS's *result*, so it writes the box
already in the LFS frame — same exemption as `normalise_for_lfs`, and it must be
commented as such.

### 1.7 API

`GET /api/files/{project}/cropbox` → `crop_box.json` (missing → `null`, like the
other analysis reads).

---

## 2. Step 4 — train inside the box

### 2.1 New `lfs` defaults

```python
class LFSDefaults(BaseModel):
    ...
    crop_enabled: bool = True
    crop_source: Literal["rc_region", "manual"] = "rc_region"
    # The box is a hard wall at the subject's surface otherwise: densification
    # needs somewhere to put the gaussians that describe the outermost surface.
    crop_margin_pct: float = 5.0
    crop_min: list[float] | None = None      # manual only
    crop_max: list[float] | None = None      # manual only
```

### 2.2 New module `backend/core/steps/lfs_crop.py`

Runs **before** `spawn()`, in `run_lfs_real` and in the stub:

1. Resolve the box: `crop_box.json` (or the manual values), inflate by
   `crop_margin_pct` about its centre.
2. Filter `rc_output/pointcloud.ply` → `rc_output/pointcloud_cropped.ply`.
3. Point the loader at it: set `"ply_file_path": "pointcloud_cropped.ply"` in
   `transforms.json`. When cropping is **off**, set it back to
   `"pointcloud.ply"` — the toggle has to be idempotent across re-runs.
4. Broadcast `[LFS] Crop box: 214 883/286 104 sparse points kept (75.1%),
   +5% margin.`
5. `< 100` points kept, or `crop_box.json` unusable → WARNING and train
   uncropped. Never fail the step on the crop.

The original `pointcloud.ply` is never modified. `pointcloud_cropped.ply` is
regenerated on every run.

### 2.3 Refactor first: `backend/core/steps/ply_io.py`

`rc_postprocess.py` already contains a correct ascii + `binary_little_endian`
PLY reader (`_read_ply_header`, `_PLY_TYPES`, the numpy structured-array path).
`lfs_crop.py` and `splat_optimise.py` both need it. Lift it into
`core/steps/ply_io.py` — `read_ply(path) -> (header, fmt, count, props, array)`
and `write_ply(path, header_lines, array, extra_comments)` — and have
`rc_postprocess` import it. **One reader, or there will be three of them within
a month.** No behaviour change; the `_ROTATED_MARKER` idempotency must survive.

### 2.4 The limitation, stated in the UI and not glossed over

This crops the **initialisation**, not the optimiser. LFS v0.5.3 has no headless
crop (verified, §0), so densification can still create gaussians outside the
box. In practice seeding inside the box does most of the work, and the export
step's crop (§3.2) is what actually guarantees the bounds. Say exactly that
under the toggle — one sentence, no marketing.

When a future LFS ships a headless crop flag, this becomes a flag and
`lfs_crop.py` becomes a fallback. Do not remove it then: the cropped init cloud
is still worth having.

---

## 3. Step 5 — gaussian optimisation

### 3.1 New `optimise` section (its own section, so it gets its own setup panel)

```python
class OptimiseDefaults(BaseModel):
    enabled: bool = False
    # builtin: our numpy pass, works today.
    # lfs: LichtFeld Studio's Splat Simplify — no CLI verb in v0.5.3 and the GUI
    # tool is bugged, so it is probed for and falls back (§3.3).
    engine: Literal["builtin", "lfs"] = "builtin"
    target_mode: Literal["ratio", "count"] = "ratio"
    target_ratio: float = 0.5            # LFS GUI default
    target_count: int = 0                # 0 = derive from ratio
    lod_base: float = 2.0                # LFS GUI default, clamp [0.1, 10.0]
    opacity_prune: float = 0.10          # LFS GUI default, clamp [0.0, 1.0]
    crop_to_region: bool = True
    sh_degree: int = -1                  # -1 keep, 0-3 reduce (LFS convert)
    convert_format: Literal["none", "ply", "sog", "spz"] = "none"
    keep_original: bool = True
```

Add `"optimise"` to `SECTIONS` and to `AppDefaults`. Field names mirror the LFS
GUI labels — Source / Target / LOD Base / Opacity Prune / Output — so the panel
and the tool speak the same language.

### 3.2 New pure module `backend/core/steps/splat_optimise.py`

Input: the trained 3DGS PLY (`x y z`, `f_dc_*`, `f_rest_*`, `opacity`,
`scale_*`, `rot_*`). Three stages, in this order, each reported separately:

1. **Crop** (`crop_to_region`) — drop gaussians whose centre is outside the
   crop box. No margin here: this is the export, the bounds are the point.
2. **Opacity prune** — drop `sigmoid(opacity) < opacity_prune`.
   **`opacity` in a 3DGS PLY is stored pre-sigmoid.** Compare after the sigmoid,
   or 0.10 silently becomes ~0.525 and half the model disappears.
3. **Target count** — keep the top-N by importance
   `sigmoid(opacity) * prod(exp(scale))` (opacity × volume), N from
   `target_count` or `round(target_ratio × original)`, clamped to
   `[1, original]` exactly like the GUI. Ties broken by original index so two
   runs on the same input give the same file.

Output `export/<stem>_<kept>.ply` — the GUI's naming (`pointcloud_1081151` in
the reference screenshot). Report:

```json
{"original": 2162302, "after_crop": 1804119, "after_prune": 1502233,
 "kept": 1081151, "bytes_before": 512000000, "bytes_after": 256000000,
 "engine": "builtin", "lod_base_applied": false}
```

`lod_base` has no meaning in the builtin engine — it is LFS's LOD-tree base.
Store it, pass it to the LFS engine, and **say in the UI that the builtin
ignores it**. Do not invent a spatial-grid interpretation to make the field look
busy.

### 3.3 `engine: "lfs"` — modelled, probed, not trusted

- `probe_lfs_simplify(lfs_exe) -> bool` — run `--help`, look for a simplify
  verb, cache the answer in `config.json` (`lfs_has_simplify`, refreshed when
  `lfs_exe_path` changes).
- Absent (v0.5.3, today) → WARNING `LichtFeld Studio v0.5.3 has no headless
  simplify; falling back to the built-in optimiser.` and run builtin.
- Present (next build) → build and run the command, map its progress onto the
  WS bus. Nothing else changes.

Should the next build expose simplify only through the Python API rather than
the CLI, the second route is `--python-script` with a generated script calling
`lf.simplify_splats(...)` and polling `lf.get_splat_simplify_progress()`. Write
the script generator behind the same probe; do **not** ship it enabled — a
Python-API call that needs a GUI scene will hang a headless run, and a hang is
worse than a missing feature.

### 3.4 SH reduction and format conversion — the part that works today

`sh_degree >= 0` or `convert_format != "none"` runs the real v0.5.3 verb:

```
LichtFeld-Studio.exe convert <in.ply> <out.<fmt>> --sh-degree 0 -y
```

Dropping SH 3 → 0 removes 45 of 59 floats per gaussian. On a 1 M-gaussian splat
that is roughly 230 MB → 60 MB, with no geometry change, using a supported code
path in the build that is installed right now. In stub mode, skip the call and
log what would have run.

### 3.5 `POST /api/pipeline/optimise`

Re-runs the optimisation alone on the splat already in `lfs_output/`, exactly as
`/analyze` re-runs curation alone. Same reason: **a target count is tuned
iteratively and no one is retraining for forty minutes to try 0.4 instead of
0.5.** Shares `_running_tasks` so one-job-at-a-time and abort keep working.

Broadcasts under step name `optimise`, mapped to step 5 in
`pipelineStore.stepNameToIndex` — same trick as `curate` → 2, no seventh step,
no renumbering.

---

## 4. Frontend

### 4.1 `Step3_RC.tsx` — "Reconstruction region"

- Mode select (`off` / `auto` / `density`), scale X-Y-Z.
- After the run: a read-only card from `crop_box.json` — source, size in scene
  units, `points_inside/points_total` with the percentage, and the `usable`
  flag as a badge. Mount it behind the same `isDone` guard as the coverage
  panel.

### 4.2 `Step4_LFS.tsx` — "Crop box"

- Enable toggle, source (From RS region / Manual), margin %.
- Manual: six numeric inputs Min X/Y/Z, Max X/Y/Z — the same six fields as the
  LFS `cropbox_controls.py` panel, same order.
- A "Fit to sparse cloud" button filling them from the percentile box.
- The §2.4 sentence, under the toggle.

### 4.3 `Step5_Export.tsx` — "Splat optimisation", laid out as the LFS GUI

Reproduce the reference panel, top to bottom:

```
Source:            pointcloud                       (read-only, the trained stem)
Target:            [======|--------]  1 081 151     slider + numeric, [1, original]
LOD Base:          [==|------------]  2.0           slider, [0.1, 10.0] step 0.1
Opacity Prune:     [=|-------------]  0.10          slider, [0.0, 1.0] step 0.01
    ┌ ORIGINAL ────────┐   ┌ TARGET ──────────┐
    │    2 162 302     │   │    1 081 151     │     two tiles, thousands separators
    └──────────────────┘   └──────────────────┘
Output:            pointcloud_1081151                (computed, read-only)
[     Apply      ]  [    Cancel    ]
```

Plus, below the LFS-matching block, the two controls LFS has no equivalent for:
`Crop to region` (toggle) and `SH degree` / `Convert format` (selects). Keep
them visually separated so the mapping to the LFS tool stays legible.

Clamps and defaults are taken from `rendering_panel.py` and must match it:
default ratio 0.5, `lod_base` 2.0 ∈ [0.1, 10.0], `opacity_prune` 0.10 ∈ [0, 1],
target ∈ [1, original], output name `<source>_<target>`.

Apply → `POST /api/pipeline/optimise`. Cancel → the existing
`/control abort`, which already kills the process tree.

### 4.4 Settings and types

- `components/settings/OptimiseSettings.tsx`, mounted in `AppSetupPanel.tsx`.
- The region fields into `RCSettings.tsx`, the crop fields into `LFSSettings.tsx`.
- `types/index.ts`: `CropBox`, `OptimiseSettings`, `OptimiseReport`,
  `StepName |= 'optimise'`.

---

## 5. Documentation to update in the same commit

- **CLAUDE.md §5** — `rc_output/region.rsbox`, `rc_output/crop_box.json`,
  `rc_output/pointcloud_cropped.ply` in the tree.
- **CLAUDE.md §8** — `GET /api/files/{project}/cropbox`,
  `POST /api/pipeline/optimise`.
- **CLAUDE.md §7.3** (new) — the region → crop-box chain, with the Rx+90 trap.
- **CLAUDE.md §12** — four rows:

| Date | Decision |
|---|---|
| 2026-08-20 | **The reconstruction region is set by RS and re-expressed in the LFS frame.** RS exports no region unless one is set, and `-setReconstructionRegionByDensity` must run after `-align`. The `.rsbox` is written in RS's Z-up frame like the sparse cloud, so it goes through the same `Rx+90`, `(x, y, z) -> (x, -z, y)` as `align_pointcloud_to_cameras` — its 8 corners, not its min/max, because the region is oriented. Without the rotation the box does not error, it deletes the scene and keeps the sky. Falls back to a percentile box from the sparse cloud, and never fails the step. |
| 2026-08-20 | **The training crop rides on `ply_file_path`, not on a CLI flag.** LFS v0.5.3 has no headless crop verb — the trainer *is* crop-aware (`CropBox filtering: {} -> {} points`) but the box is a GUI scene node. The Blender/NeRF loader reads `ply_file_path` from `transforms.json` (default `pointcloud.ply`), so step 4 writes `pointcloud_cropped.ply` and repoints that key, leaving the original untouched. This crops the initialisation, not the optimiser: the export-step crop is what bounds the final splat, and the UI says so. |
| 2026-08-20 | **Splat optimisation ships with a built-in engine and an LFS engine behind a probe.** LFS's Splat Simplify is a Python-API call (`lf.simplify_splats(ratio, lod_base, opacity_prune_threshold)`), not a CLI verb, and is bugged in v0.5.3. The built-in numpy pass — crop, opacity prune on the **post-sigmoid** value, then top-N by opacity × volume — works today; `--help` is probed for a simplify verb and the engine switches with no code change when the next build lands. `lod_base` is LFS-only and the UI says the built-in ignores it rather than faking a meaning for it. |
| 2026-08-20 | **Optimisation is re-runnable alone (`POST /api/pipeline/optimise`), broadcasting under the step name `optimise` mapped to step 5.** Same shape and same reason as `/analyze` → `curate` → step 2: a target count is tuned iteratively and no one retrains for forty minutes to try another ratio. |

- **CLAUDE.md §10** — **no new dependency.** numpy, OpenCV and the rest are
  already in the table; the PLY work is numpy and the conversions are the LFS
  exe as a subprocess. If that stops being true, the row lands before the code.
- **TODO.md** — the P1 COLMAP export item now has a second reason to exist: the
  COLMAP loader path reads `points3D.{bin,txt,ply}`, so the crop would move
  from `ply_file_path` to writing a cropped `points3D`. Note it, do not do it
  here.

---

## 6. Acceptance

**Stub (no GPU, all four stubs on):**

1. Step 3 writes `region.rsbox` + `crop_box.json` with `usable: true` and a
   coverage between 0 and 1.
2. Step 4 writes `pointcloud_cropped.ply`, `transforms.json.ply_file_path`
   points at it, and the log shows the kept/total counts.
3. Toggling the crop off and re-running step 4 puts `ply_file_path` back to
   `pointcloud.ply` — idempotent both ways.
4. Step 5 with `optimise.enabled` writes `export/<stem>_<N>.ply` with exactly N
   gaussians, and the original is still there with `keep_original`.
5. `POST /api/pipeline/optimise` re-runs on the existing splat without touching
   `lfs_output/`.

**Real tools:**

6. RS produces a `.rsbox` that parses; the box drawn from `crop_box.json`
   contains the subject and not the horizon — check `coverage`, and check the
   cropped cloud opens in the LFS viewer aligned with the cameras. **If the
   cropped cloud is 90° off from the cameras, the rotation of §1.3 is wrong —
   that is the one failure this whole session hinges on.**
7. LFS trains from the cropped cloud and does not log
   `No camera intrinsics found` (the §7.2 normalisation must still run first).
8. `convert --sh-degree 0` produces a file that loads in SuperSplat and in the
   Blender importer.
9. An unusable box (coverage < 5 %) warns and trains uncropped, and the pipeline
   completes.

**Regression:**

10. `rc_postprocess`'s rotation stays idempotent after the `ply_io.py` refactor —
    running step 3 twice must not rotate the cloud twice.
11. `alignment_check.json` is unchanged: the coverage check compares input
    frames against the registration and has nothing to do with the region.
12. Abort during step 5's optimisation kills the process tree and leaves the
    step `aborted`, not `error`.

---

## 7. Known traps, collected

1. **The Rx+90.** §1.3. The single most likely way to ship this broken.
2. **RS exports no region unless one is set.** `-exportReconstructionRegion`
   alone yields nothing and RS still exits 0.
3. **`.rsbox` vs `.rcbox`.** RealityScan 2.2 renamed it. Read both.
4. **Pre-sigmoid opacity** in the 3DGS PLY. §3.2.
5. **`ply_file_path` is relative to the transforms.json directory**, like the
   image paths `normalise_transforms` already relativises.
6. **Cropping the init cloud does not bound the trained model.** Say it, don't
   sell it.
7. **A zero exit code from LFS is still not success** (CLAUDE.md §12,
   2026-08-20). The `convert` calls need the same suspicion: check the output
   file exists and is non-empty.
8. **`projects/` is sacred.** The optimiser writes new files next to the
   originals; it never overwrites `lfs_output/`.
