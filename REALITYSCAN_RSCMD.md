# The `.rscmd` — how this app drives RealityScan

Contributor's guide to step 3. Everything here was measured against
**RealityScan 2.2** on the project workstation; where a value is inferred
rather than measured, it says so.

The spec is [CLAUDE.md](CLAUDE.md) (§7.1, §7.2, §15.3). This file is the detail
behind it: what the generated script contains, why the lines are in that order,
and what breaks when they are not.

---

## 1. Where it comes from

Nothing is shipped as a static file. Every run regenerates both artefacts:

| Artefact | Written by | Path |
|---|---|---|
| The command script | `build_rscmd`, [`backend/core/steps/step_rc.py`](3dgs-pipeline-app/backend/core/steps/step_rc.py) | `projects/<slug>/rc_output/align.rscmd` |
| The COLMAP export params | `build_colmap_export_params`, [`backend/core/steps/rc_export_params.py`](3dgs-pipeline-app/backend/core/steps/rc_export_params.py) | `projects/<slug>/rc_output/colmap_export_params.xml` |

They are generated because they are *user-facing settings*: `-mergeComponents`
is absent from some RealityScan builds and an unknown verb makes RS exit
non-zero, so the merge has to be switchable from the UI rather than by
hand-editing a file. The same argument covers every other knob.

Both files stay in `rc_output/`, so a re-alignment resets them with the rest of
step 3.

### How it is launched

```
RealityScan.exe -writeProgress "<rc_output>\rc_progress.txt" 1 \
                -headless \
                -execRSCMD "<rc_output>\align.rscmd"
```

`RealityScan.exe` is a **GUI-subsystem binary**: it has no console, so the
`readline()` loop over its stdout sees one EOF and nothing else. The progress
file is the only channel that works — see §6.

### File format

One verb per line, UTF-8, LF-terminated, every path **absolute and quoted**.
RS reads the script top to bottom and **aborts the whole script on a verb it
does not know**. That single fact explains most of the ordering below.

---

## 2. The structure

| # | Line | Emitted when |
|---|---|---|
| 1–4 | `-set "sfmFeatureDetectionQuality=…"`<br>`-set "sfmMaxFeaturesPerMpx=…"`<br>`-set "sfmMaxFeaturesPerImage=…"`<br>`-set "sfmImagesOverlap=…"` | always |
| 5 | `-addFolder "<project>\frames"` | always |
| 6 | *extra lines* | one per non-empty `rc.extra_align_commands`, verbatim |
| 7 | `-align` | always |
| 8 | `-mergeComponents` | `rc.merge_components` |
| 9 | `-selectMaximalComponent` | `rc.keep_largest` |
| 10 | `-save "<rc_output>\<slug>.rsproj"` | `rc.save_project` |
| 11 | `-exportRegistration "<rc_output>\transforms.json"` | always — the NeRF export |
| 12 | `-exportSparsePointCloud "<rc_output>\pointcloud.ply"` | always |
| 13 | `-exportRegistration "<rc_output>\<slug>_COLMAP\colmap.txt" "<rc_output>\colmap_export_params.xml"` | `rc.colmap.enabled` |
| 14 | `-clearCache` | always |
| 15 | `-quit` | always |

### A real one — all options on

```
-set "sfmFeatureDetectionQuality=Normal"
-set "sfmMaxFeaturesPerMpx=30000"
-set "sfmMaxFeaturesPerImage=60000"
-set "sfmImagesOverlap=Medium"
-addFolder "G:\...\projects\fauteuil3d_test\frames"
-align
-selectMaximalComponent
-save "G:\...\rc_output\fauteuil3d_test.rsproj"
-exportRegistration "G:\...\rc_output\transforms.json"
-exportSparsePointCloud "G:\...\rc_output\pointcloud.ply"
-exportRegistration "G:\...\rc_output\fauteuil3d_test_COLMAP\colmap.txt" "G:\...\rc_output\colmap_export_params.xml"
-clearCache
-quit
```

The generated script is echoed into the LiveLog at the start of the step, so
the exact text of any past run is readable from the UI as well as from
`rc_output/align.rscmd`.

---

## 3. Why the order is what it is

**`-set` before `-addFolder`.** They are RS *application* settings and the CLI
has no per-project scope for them — what a run sends is what the RS GUI's
Alignment Settings panel shows next time it is opened by hand. Putting them
first also means `rc.extra_align_commands` (line 6) can override any of them.

**`extra_align_commands` before `-align`.** It is the escape hatch for verbs
the app does not model — marker import, alignment parameters we have not
exposed — and everything it could plausibly set has to be in place before the
alignment runs.

**One `-align`, never several.** Image groups in RS are *calibration* groups
inside one project; they do not partition the reconstruction. The sequences
curation found in step 2 never split the script (CLAUDE.md §7.1). What the
sequence count drives is `sfmImagesOverlap`, not the script's shape.

**`-save` before the exports, not after.** RS aborts the script on an unknown
verb, and `-mergeComponents` above is exactly the verb some builds reject. An
alignment that took an hour must survive an export that never runs. Everything
after this line is a file written beside the project, so nothing is lost by
saving early.

**The COLMAP export into its own `<slug>_COLMAP\` subfolder.** Both
`-exportRegistration` calls write undistorted images named `00000.png`,
`00001.png`… The NeRF one drops them beside `transforms.json`; the COLMAP one
writes the same basenames under `images/`. Share a directory and LichtFeld
Studio refuses the dataset outright:

```
COLMAP dataset contract violation: image '…' is ambiguous under '…'
```

**Both exports, always.** The COLMAP dataset is what step 4 trains on — one
intrinsic per image (CLAUDE.md §7.2). `transforms.json` is what the coverage
check, the camera overlay and the 3D preview read, and it is step 4's fallback,
with a warning naming the defect, when no COLMAP dataset is found.

**`-clearCache` at the end.** RS keeps a resource cache across sessions and it
belongs to the *application*, not the project. Clearing it here — after the
`-save`, which is what RS's own help asks for — releases it once the run has no
further use for it. The trade-off: it no longer protects an alignment from a
stale cache entry left by an earlier run of the same frames.

---

## 4. The four `-set` keys

The names come from the installed help,
`Help/en-US/tutorials/setkeyvaluetable.htm`, section *Alignment Settings* —
**not** from the GUI labels, which differ. A key RS does not know is an error
and stops the script, so `_alignment_settings()` in `step_rc.py` is the one
place they are spelled.

| CLI key | GUI label | Setting | Default | Note |
|---|---|---|---|---|
| `sfmFeatureDetectionQuality` | Feature detection quality | `rc.feature_detection_quality` | `High` | **Two values only** in RS 2.2: `Normal`, `High`. There is no "Preview" quality — the old `precision` field claimed one, and it is gone |
| `sfmMaxFeaturesPerMpx` | Max features per mpx | `rc.max_features_per_mpx` | `30000` | The budget that actually bites on a 4K frame. RS's own default is 10 000; 30 000 is this workstation's tuned value |
| `sfmMaxFeaturesPerImage` | Max features per image | `rc.max_features` | `60000` | A ceiling on top of the per-mpx budget |
| `sfmImagesOverlap` | Images' overlap | `rc.image_overlap` | `Medium` | `Low` / `Medium` / `High`. The first thing to raise on an alignment that split: across a cut, frame *k* and *k+1* are unrelated, so sequential preselection has nothing to work with |

Until 2026-08-24 the `.rscmd` contained none of these: two of them were on
screen in the settings panels and reached nothing, and every alignment ran on
whatever the RS GUI had last been left on.

---

## 5. The COLMAP export-params XML

`-exportRegistration <file> <config file>` takes a **settings** file — the one
the Export Registration dialog writes — *not* a format definition. Handing it a
format definition produces

```
Loading of the configuration from the file 'colmap_export_params.xml' failed. [err:5617]
```

after which RS holds the batch open on a modal, so the step never returns. In
an earlier form it **skipped the export without failing the script**: step 4
silently fell back to the NeRF loader and trained badly for weeks.

The shape that works is the one every RS tool that can save its settings uses
(see `Settings/SimplifiedExport/*.xml` in the install):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration id="{280B11A4-F9A3-47D1-AE58-C0DEA33487D8}">
  <entry key="colmapDirStructure" value="CDS_STANDARD" />
  <entry key="colmapFileType" value="CFT_TXT" />
  <entry key="colmapPointFiltering" value="1" />
  <entry key="exportUndistorted" value="1" />
  <entry key="undistFitMode" value="1" />
  <entry key="undistortNamingConvention" value="00000" />
  <entry key="MvsExportRotationX" value="180.000000" />
  …
</Configuration>
```

The `id` is the format GUID from `calibration.xml`, next to `RealityScan.exe`:

```xml
<format id="{280B11A4-F9A3-47D1-AE58-C0DEA33487D8}" mask="*.txt"
        descID="9001" desc="COLMAP" writer="RealityScan.Export.COLMAP"
        undistortImages="1" exportImages="1" requires="component"/>
```

It is not validated when the configuration is read — a wrong GUID and no GUID
at all both load — but it is the only thing that can say *which* exporter to
run: `calibration.xml` gives the `*.txt` mask to both COLMAP and Boujou, so the
output path cannot disambiguate them.

Four things to know before touching this file:

- **Values are not validated either.** A misspelt enum token is *ignored*, not
  refused, so a wrong one shows up as an output that does not match the request
  and never as an error. `verify_against_saved_params()` at the bottom of
  `rc_export_params.py` compares our keys against an XML saved from the dialog;
  that saved file is the only authority on the tokens.
- **`CFT_BIN` is known to be wrong.** Asking for binary produced a *text* model
  every time. Every file of the install was searched and the only `CFT_`/`CDS_`
  /`CME_` tokens that exist are `CFT_TXT`, `CDS_STANDARD` and `CME_EXT` — the
  three defaults. The counterparts are not in the binary at all, so their real
  spelling cannot be recovered from it. `defaults.json` therefore asks for
  `ascii`, which is what RS writes either way, and `check_colmap_export` warns
  on a mismatch — so the knob starts working the day the token turns up instead
  of lying in the meantime. The cost of staying on text is `images.txt` at
  ~73 MB and `points3D.txt` at ~36 MB per run.
- **Undistortion is not a preference.** RS refuses to write a COLMAP camera for
  its own `division` distortion model and falls back to camera-model id 13,
  which is not one of COLMAP's twelve; LFS answers `Invalid camera model ID 13
  for image`.
- **`MvsExportRotationX = 180` is what keeps the splat upright.** RS's COLMAP
  template hard-codes `(x, y, z) -> (x, -z, y)`, which puts the world Y-down.
  LFS's *NeRF* loader cancels that with its own `Rx+180`; its *COLMAP* loader
  does not, because COLMAP is already the convention it wants. The dialog's
  180° composes to `Rx-90` overall and lands both routes in the same world
  frame — so `viewer/frame.ts`, `export/` and Blender all stay as they are. It
  is exposed as `rc.colmap.scene_rotate_x_deg` rather than hardcoded, for the
  shoots where RS's +Z was never the vertical.

Every parameter is emitted in full, the identity ones included: an absent
parameter lets RS fall back to whatever the export dialog was last set to by
hand, which is exactly the state a generated run must not inherit.

---

## 6. The script is also the progress plan

`rc_progress.plan_from_script()` re-reads the text `build_rscmd` just wrote and
turns it into the expected task list. That is why the script's shape and the
progress bar cannot drift apart — **add a verb and the bar accounts for it on
its own.**

RealityScan reports through `-writeProgress "<file>" 1`, one line per update:

```
<task id> <fraction> <elapsed s> <estimated remaining s> #<state>

65537 0.00 0.01 142.40 #started
65537 0.41 12.52 18.38 #progress
65537 1.00 26.14 0.00  #completed
```

Measured on `fauteuil3d_test`, 251 frames, 106 s end to end:

| Task id | Verb | This run | Weight |
|---|---|---|---|
| `41061`, `41063`, `41064` | RS booting — **not** a phase; present when `-quit` is the whole script | 0.00 s ×3 | ignored |
| — | `-set` | emits no task at all | — |
| `65536` (0x10000) | `-addFolder` | 0.19 s | 2 |
| `65537` (0x10001) | `-align` | **89.95 s** | 70 |
| `20533`, `20534` | `-selectMaximalComponent`, `-save` (not separable) | 0.10 / 0.59 s | 1 / 2 |
| `20576` (0x5060) | `-exportRegistration` — it undistorts and rewrites every image | 9.79 s | 12 |
| `20585` (0x5069) | `-exportSparsePointCloud` | 0.37 s | 2 |
| — | `-clearCache` | not separately measured | 1 |

**The id is the stable key; the ordinal is not.** The ids repeated byte for
byte across four separate processes, while `-align` moved from task 2 of 3 to
task 5 of 9 as verbs were added around it. So each incoming id claims the next
plan entry *of its own kind*. That resync is not decoration: a verb RS refuses
is skipped **without failing the script** — the `err:5617` COLMAP export was
exactly that — and a bar keyed on the ordinal alone would credit the
alignment's weight to the wrong phase for the rest of the run.

The trailing `1` is a **heartbeat period in seconds, not a write interval**: RS
writes every change with or without it, and the `#timeout` lines it adds are
what distinguish a plateau from a hang (the alignment sat at `0.55` for 20 s).
`-writeProgress <file> 1000` creates the file and writes **0 bytes** for the
whole run, which is what made the feature look absent.

Two channels that do **not** work, recorded so nobody measures them twice:
`-printProgress` reaches the pipe but the CRT full-buffers it into 4 KB flushes
and a whole alignment emits ~3 KB (one update, late); and
`%TEMP%\RealityScan.log` is frozen at the same byte count for the entire
reconstruction.

The weights live in `rc_progress.py`, not in `defaults.json`: they measure the
tool, like the 5–95 % mapping of the LichtFeld bar, and nobody wants a slider
for them. They are relative and renormalised over whatever the script actually
contains, so a run with two registration exports is weighted without a second
table.

---

## 7. After the script — what step 3 still does

The `.rscmd` ends at `-quit`; the step does not. In order:

1. **`rc_postprocess.normalise_transforms`** — RS writes `camera_model:
   SIMPLE_RADIAL` with the intrinsics *inside each frame*, while LFS's NeRF
   loader reads them once, at top level. Hoists the medians, names the model
   `PINHOLE` (`OPENCV` if any `k`/`p` is non-zero) and rewrites the absolute
   `G:\…` image paths relative to `rc_output/`. Gated on `rc.normalise_for_lfs`.
2. **`rc_postprocess.align_pointcloud_to_cameras`** — `pointcloud.ply` comes
   out in RS's Z-up frame while `transforms.json` is NeRF Y-up. Rotates the
   cloud `Rx+90`, `(x, y, z) -> (x, -z, y)`, and stamps it in the PLY header so
   a re-run is a no-op.
3. **`check_colmap_export`** — is the dataset actually there, and does the model
   written match the one requested (§5). Warns, never fails.
4. **The coverage check** — `-selectMaximalComponent` keeps the largest
   component and **silently drops the rest**. Step 3 compares the frames fed in
   against the cameras in the exported registration and writes
   `rc_output/alignment_check.json`. It warns and does not fail: a handful of
   unalignable frames must not block the pipeline, and the call to re-align is
   the user's.

Note that `run_rc` calls `reset_steps(project_path, [3])` before writing the
script and **after** locating the exe — RS writes into `rc_output/` without
clearing it, so a 300-frame run over a previous one would leave orphaned
`00300.png`… behind, and a misconfigured tool path must not cost the alignment
already on disk.

---

## 8. Changing the script — the checklist

- **A new verb** → add it to `build_rscmd`, then give it a weight and a label in
  `rc_progress.WEIGHTS` / `LABELS`. An unknown verb gets `_DEFAULT_WEIGHT`,
  which is wrong by a couple of percent, not broken.
- **A new knob** → a field on `RCDefaults` (with the reason in a comment), a
  value in `defaults.json`, a control in the RealityScan settings panel. A key
  the model does not know is dropped by `resolve_rc_settings`, which is what
  keeps a stale project row from reaching the script.
- **Anything switchable that RS might reject** → put it *after* `-save`, or
  accept that a build without that verb loses the alignment.
- **Never** point the two `-exportRegistration` calls at the same directory,
  and never drop the NeRF one: three readers depend on it.
- Regenerate a script without running RS:

  ```python
  from pathlib import Path
  from backend.core.defaults import RCDefaults
  from backend.core.steps.step_rc import build_rscmd
  from backend.core.steps.rc_progress import plan_from_script

  s = build_rscmd(Path("frames"), Path("out"), Path("out/x_COLMAP"), RCDefaults(), "demo")
  print(s.read_text())
  print(plan_from_script(s.read_text()))
  ```

- Probe RS itself cheaply: a script of `-quit` alone still emits the three
  startup tasks, which is how the "not a phase" list in §6 was established.

---

## 9. Dead ends, recorded so they are not re-explored

| Idea | Verdict |
|---|---|
| A static `.rscmd` shipped with the app | `-mergeComponents` is missing from some builds and an unknown verb aborts the script — it has to be generated |
| One image group per sequence | Groups are *calibration* groups; they do not partition the reconstruction, and splitting the calibration of a single-camera video is strictly worse |
| Merging two components from the CLI | No usable verb. Control points shared by both components, placed in the GUI, then re-align. Two chunks that never see the same surface cannot be merged by any setting — that one is a shoot-side answer |
| Tailing `%TEMP%\RealityScan.log` for progress | Silent for the entire reconstruction |
| `-printProgress` | CRT full-buffering: one flush, late |
| `RealityScan.exe -getStatus <name>` | Answers in 170–470 ms without disturbing the run, but reports only the *current* task, so it can count nothing — and it costs a whole `RealityScan.exe` per poll. It does prove the delegate family works headless, which makes `pauseInstance` / `unpauseInstance` / `abortInstance` real. Reviving Pause for step 3 is a feature, not a wiring fix |
| Asking for a binary COLMAP model | `CFT_BIN` is not RS's token; the export comes out ASCII either way (§5) |
