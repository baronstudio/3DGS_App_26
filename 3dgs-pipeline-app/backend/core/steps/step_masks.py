"""step_masks.py — masks made by RealityScan itself, from the region and a mesh.

The second half of TODO P4, and the only mask route for a project that started
from a *video*, where there never was an alpha channel to lose.

**A second RealityScan process, not a longer step 3.** The mesh is minutes and
nobody wants to re-align to change a mask, so this reopens the `.rsproj` step 3
saved and works from there — modelled on `/api/pipeline/analyze`, which is the
existing precedent for re-running one phase without redoing the expensive one
(CLAUDE.md 6.3). It reports under the step name `masks`, mapped to wizard step 3
exactly as `curate` maps to step 2.

## The script, and why it is not the one TODO P4 sketched

    -load "<rc_output>/<slug>.rsproj"
    -set  "mvsPreviewDownscaleFactor=…" / "mvsNormalDownscaleFactor=…"
    -set  "MvsGeometryGpuAccel=…"
    [-setReconstructionRegion "<region>/region.rsbox"]
    -calculatePreviewModel | -calculateNormalModel | -calculateHighModel
    -selectAllImages
    -generateMaskFromMesh
    -exportRegistration "<dataset>/colmap.txt" "<mask_export_params.xml>"
    [-save "<rc_output>/<slug>.rsproj"]
    -quit

TODO P4's last two lines were `-exportMapsAndMask <folder> <params.xml>` and
then a delivery of that folder into the dataset. Measured on RealityScan
2.2.0.119430, on `publicsemple_truck` with a real preview mesh and every image
selected, that verb writes `imageList.txt` and answers

    Exporting Depth, Normal and Mask Images failed after 0.286 seconds.
    Processing failed: Feature not implemented.

— in a window, on top of everything else, because RealityScan surfaces a batch
error in its GUI even under `-headless`. The `ei*` keys it was given were not
the problem: `eiExportImageList` was honoured, which is how `imageList.txt` got
written. The exporter is simply not there in this build.

What *is* there is `colmapExportMasks`, an option of the COLMAP exporter step 3
already drives. `-generateMaskFromMesh` adds a mask *layer* to every image in
the project; re-running the COLMAP export with that option writes those layers
into `<dataset>/masks/`, through **the same undistortion block** as `images/`
and under **the same names**. Both of TODO P4's stated risks — "will the masks
come out in the undistorted geometry" and "will the names meet" — stop being
questions to answer and become properties of the export.

The price is that the mask run rewrites the whole COLMAP dataset, `images/` and
`sparse/` included. Measured: 4.3 s on 251 images of ~1 Mpx, against 9.79 s for
the same export on 251 4K frames in CLAUDE.md 15.3. It is also the honest
behaviour — a dataset whose masks were exported in one pass with its images
cannot drift from them.

## What still has to be repaired afterwards

The masks come out at **half** the image size — `973x543` image, `486x271`
mask, one for one over 251 images. Neither `mvsPreviewDownscaleFactor=1` nor
`txtImageDownscaleColor=1` changes it, so it is the mask layer's own
resolution. LichtFeld Studio refuses a size mismatch outright, so
`rc_alpha.fit_dataset_masks` resizes them in place. See its docstring.

## Not `-clearCache`

The alignment script ends with it; this one must not. Measured: after a mesh
has been calculated, `-clearCache` answers *"Cache contains current scene
modifications. [err:5607]"*, fails the script and pops RealityScan's crash
reporter. The cache is the application's, step 3 clears it, and it is not worth
a crash dialog here.

Pure module: no FastAPI, `broadcast_fn` injected, like every other step.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from backend.core.config import app_config
from backend.core.defaults import RCDefaults
from backend.core.proc import (
    ProcessAborted,
    iter_lines,
    kill_tree,
    release,
    spawn,
)
from backend.core.steps import colmap_dataset
from backend.core.steps import rc_alpha
from backend.core.steps import rc_region
from backend.core.steps.rc_export_params import (
    build_mask_export_params,
    check_format_registered,
)
from backend.core.steps.rc_progress import RCProgressTracker, plan_from_script
from backend.core.steps.step_rc import (
    _classify_rc_line,
    check_colmap_export,
    _missing_format_note,
    resolve_rc_settings,
    tail_progress,
)

STEP_NAME = "masks"

# Written into rc_output/ like the alignment's, so a reset of step 3 takes it.
_PROGRESS_FILENAME = "masks_progress.txt"
_SCRIPT_FILENAME = "masks.rscmd"
_PARAMS_FILENAME = "mask_export_params.xml"

# `-calculate*Model`, by `rc.masks.mesh_quality`.
_MESH_VERBS = {
    "preview": "-calculatePreviewModel",
    "normal": "-calculateNormalModel",
    "high": "-calculateHighModel",
}


class MaskRunError(RuntimeError):
    """A precondition this run cannot supply for itself."""


def project_file(rc_output: Path, project_name: str) -> Path:
    """The `.rsproj` step 3 saved — the input this whole run is built on.

    The expected name first, then any other `.rsproj` in `rc_output/`, for the
    same reason `colmap_dataset.find_dataset` accepts any `*_COLMAP`: a copied
    project keeps the file the *original* wrote, and matching on the slug alone
    would answer "no saved alignment" for a project that has a perfectly good
    one. Returns the expected path when there is nothing else, so the caller
    always has a name to put in its error.
    """
    expected = rc_output / f"{project_name}.rsproj"
    if expected.exists() or not rc_output.is_dir():
        return expected
    others = sorted(rc_output.glob("*.rsproj"))
    return others[0] if others else expected


def _mesh_settings(rc: RCDefaults) -> list[str]:
    """`-set` lines for the three mesh knobs the app owns.

    Keys from Help/en-US/tutorials/setkeyvaluetable.htm ("Image depth map
    calculation", "Mesh calculation"), not from the GUI labels — a key RS does
    not know is an error and stops the script.

    Application settings, like the alignment's four (step_rc._alignment_settings):
    what a run sends is what the RS GUI shows afterwards.
    """
    masks = rc.masks
    return [
        f'-set "mvsPreviewDownscaleFactor={masks.preview_downscale}"',
        f'-set "mvsNormalDownscaleFactor={masks.normal_downscale}"',
        f'-set "MvsGeometryGpuAccel={"true" if masks.gpu_acceleration else "false"}"',
    ]


def build_masks_rscmd(
    rc_output: Path,
    dataset: Path,
    region_file: Path | None,
    rc: RCDefaults,
    project_name: str,
) -> Path:
    """Write the mask script and return its path.

    Generated per run from the settings, exactly like `align.rscmd`
    (CLAUDE.md 12): the mesh quality, the region and the save are all
    switchable, and a static file would have to be hand-edited.

    `region_file` is None when the user placed no box — the saved project
    already carries whatever region step 3 fitted, so the run simply does not
    send the verb.
    """
    params = build_mask_export_params(rc.colmap, rc_output / _PARAMS_FILENAME)

    lines = [f'-load "{project_file(rc_output, project_name)}"']
    lines += _mesh_settings(rc)
    if region_file is not None:
        lines.append(f'-setReconstructionRegion "{region_file}"')
    lines.append(_MESH_VERBS[rc.masks.mesh_quality])
    # Without it the export is empty or partial and RS does not say so: the
    # mask layers are generated for, and exported for, the *selected* images.
    lines.append("-selectAllImages")
    lines.append("-generateMaskFromMesh")
    lines.append(f'-exportRegistration "{dataset / "colmap.txt"}" "{params}"')
    # After the export, not before: the export is the deliverable, and RS
    # aborts the script on a verb it dislikes. Saving here keeps the mesh and
    # the mask layers, so a re-export costs the export alone.
    if rc.masks.save_project_after:
        # Back onto the file that was opened, not onto the expected name: a
        # copied project's alignment lives under the original's slug, and
        # saving beside it would leave two projects in one rc_output/ with the
        # newer one invisible to the load above.
        lines.append(f'-save "{project_file(rc_output, project_name)}"')
    lines.append("-quit")

    script = rc_output / _SCRIPT_FILENAME
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return script


def _resolve_exe() -> Path:
    rc_exe_str = app_config.tools.rc_exe_path
    if not rc_exe_str:
        raise FileNotFoundError(
            "rc_exe_path is not configured.\n"
            "Install RealityScan via the Epic Games Launcher and set rc_exe_path in Settings."
        )
    rc_exe = Path(rc_exe_str)
    if not rc_exe.exists():
        raise FileNotFoundError(
            f"RealityScan.exe not found at: {rc_exe}\n"
            "Install RealityScan via the Epic Games Launcher and set rc_exe_path in Settings."
        )
    return rc_exe


async def run_mask_generation(project_path: Path, broadcast_fn, settings: dict) -> dict:
    """Reopen the alignment, mesh inside the region, and export the masks.

    Fails loudly on the three things it cannot do without — the exe, the saved
    project and the COLMAP dataset — because each of them has a one-line answer
    the user can act on, and none of them is worth silently re-aligning for.
    """
    rc_exe = _resolve_exe()
    rc = resolve_rc_settings(settings)
    rc_output = project_path / "rc_output"

    if not rc.colmap.enabled:
        raise MaskRunError(
            "The COLMAP export is off in the RealityScan settings, and it is "
            "what carries the masks: RealityScan writes them into the "
            "dataset's masks/ folder as part of that export. Turn it on and "
            "re-run step 3."
        )

    rsproj = project_file(rc_output, project_path.name)
    if not rsproj.exists():
        raise MaskRunError(
            f"No saved RealityScan project at {rsproj}. The mask run reopens "
            f"the alignment rather than repeating it, so there has to be one: "
            f"re-run step 3 with 'Save the .rsproj' on (rc.save_project)."
        )

    dataset, report = colmap_dataset.find_dataset(project_path)
    if not report["found"]:
        # A re-run of step 3 is the answer only when the export *can* work.
        # When this install does not register the COLMAP format there is
        # nothing to re-run: RS will write the same image list again, silently
        # (rc_export_params.check_format_registered).
        registry = check_format_registered(rc_exe)
        note = (
            _missing_format_note(registry)
            if registry["checked"] and not registry["registered"]
            else None
        )
        raise MaskRunError(
            f"No COLMAP dataset to put the masks in ({report['reason']}). "
            f"Expected it at {dataset} — re-run step 3 with the COLMAP export "
            f"enabled."
            + (f"\n\n{note}" if note else "")
        )

    region_file = None
    directory = rc_region.region_dir(project_path)
    placed = directory / rc_region.REGION_RSBOX_FILENAME
    if rc.masks.use_region and placed.exists():
        region_file = placed
        await broadcast_fn(
            STEP_NAME, "INFO",
            f"[RS] Meshing inside the region you placed (region/{placed.name}).",
        )
    else:
        why = (
            "the region is turned off for this run"
            if not rc.masks.use_region
            else "no box has been validated for this project"
        )
        await broadcast_fn(
            STEP_NAME, "INFO",
            f"[RS] No reconstruction region is sent ({why}) — RealityScan will "
            f"mesh inside whatever region the saved project already carries. "
            f"Place a box in the viewer above to control what the masks keep.",
        )

    # A re-run is a reset of the masks, for the same reason a re-alignment is a
    # reset of step 3 (CLAUDE.md 12, 2026-08-23): RS writes into masks/ without
    # clearing it, so a run over a shorter image set would leave the previous
    # run's masks beside the new ones — and every one of them pairs with an
    # image by name, so the orphans would be delivered to LichtFeld Studio as
    # though they described this export. After the preconditions, never before.
    masks_dir = dataset / "masks"
    if masks_dir.is_dir():
        shutil.rmtree(masks_dir, ignore_errors=True)

    script = build_masks_rscmd(
        rc_output, dataset, region_file, rc, project_path.name
    )
    await broadcast_fn(
        STEP_NAME, "INFO",
        "[RS] Script:\n  " + script.read_text(encoding="utf-8").strip().replace("\n", "\n  "),
    )
    await broadcast_fn(
        STEP_NAME, "INFO",
        "[RS] The whole COLMAP dataset is re-exported, images and sparse "
        "model included — that is what puts the masks through the same "
        "undistortion as the images they mask.",
    )

    progress_file = rc_output / _PROGRESS_FILENAME
    cmd = [
        str(rc_exe),
        "-writeProgress", str(progress_file), "1",
        "-headless",
        "-execRSCMD", str(script),
    ]
    await broadcast_fn(STEP_NAME, "INFO", f"[RS] Launching: {' '.join(cmd)}")

    loop = asyncio.get_running_loop()
    proc = spawn(cmd, project_path)

    tracker = RCProgressTracker(plan_from_script(script.read_text(encoding="utf-8")))
    stop = asyncio.Event()
    tail = asyncio.create_task(
        tail_progress(progress_file, tracker, broadcast_fn, stop, STEP_NAME)
    )

    try:
        async for line in iter_lines(proc, loop):
            await broadcast_fn(STEP_NAME, _classify_rc_line(line), line)

        returncode = await loop.run_in_executor(None, proc.wait)
        stop.set()
        await asyncio.wait_for(tail, timeout=2)
    except asyncio.CancelledError:
        kill_tree(proc)
        raise
    except asyncio.TimeoutError:
        pass
    finally:
        if not tail.done():
            tail.cancel()
        killed = release(project_path, proc)

    if killed:
        raise ProcessAborted("RealityScan was stopped by the user.")
    if returncode != 0:
        raise RuntimeError(f"RealityScan exited with code {returncode}")

    # RS skips an export it dislikes without failing the script (the err:5617
    # of CLAUDE.md 12, 2026-08-23), and this run rewrote the dataset step 4
    # trains on — so what came out is checked before anything is claimed.
    colmap = await check_colmap_export(project_path, rc, broadcast_fn, STEP_NAME)
    fitted = await asyncio.to_thread(rc_alpha.fit_dataset_masks, dataset)

    level = {"ready": "SUCCESS", "partial": "WARNING"}.get(fitted["state"], "WARNING")
    await broadcast_fn(STEP_NAME, level, f"[RS] {fitted['note']}")

    if fitted["state"] == "ready":
        await broadcast_fn(
            STEP_NAME, "SUCCESS",
            f"[RS] Masks ready in {dataset.name}/masks/ — step 4 will send "
            f"--mask-mode without any further work.",
            progress=1.0,
        )
    else:
        await broadcast_fn(
            STEP_NAME, "WARNING",
            "[RS] The mask run finished but the dataset does not carry a usable "
            "mask per image. Step 4 will train without masks.",
            progress=1.0,
        )

    return {
        "dataset": str(dataset),
        "masks": fitted,
        "colmap": colmap,
        "region": str(region_file) if region_file else None,
        "mesh_quality": rc.masks.mesh_quality,
    }
