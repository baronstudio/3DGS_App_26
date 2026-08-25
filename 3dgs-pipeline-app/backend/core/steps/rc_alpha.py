"""Does the alpha channel survive RealityScan, as far as the dataset step 4 trains on?

**RealityScan is not the consumer of the alpha.** It has no concept of an alpha
channel on a *source* image — its masks are a separate layer, and that is not
this workflow. The alpha of an imported PNG set exists for one reason: to reach
LichtFeld Studio as a training mask, and the only road there is *inside the
images*, through RS's COLMAP export. RS undistorts and rewrites every frame on
the way out; either the channel comes out the other side or it does not.

When the channel *does* survive, there is nothing to do: LichtFeld Studio reads
it off the images ("Using alpha channel as mask source").

When it does not, step 2's extracted alpha images (`projects/<slug>/masks/`)
are the second copy — but they are only usable if they still match the images
they are masks of, and that is not guaranteed. RS undistorts on the way out and
crops every image differently: measured on `coutryside_001` (§7.2), frame 0
came out 3793×2835 and frame 1 3785×2831 from a source of one uniform size. A
mask of the wrong geometry is worse than no mask — it deletes real surface and
keeps background — and LichtFeld Studio refuses it anyway: `Mask '{}' is {}x{}
but image '{}' is {}x{}`.

So `deliver_masks` compares the dimensions before it copies anything. It is not
a formality: a PNG set carrying alpha is very often a *render*, i.e. already
pinhole, where RS's undistortion is close to a no-op and the sizes do line up.
When they do not, the answer is on RS's side — masks generated from the
Reconstruction Region and the mesh, exported by RS itself and therefore in RS's
own geometry. That is a feature of its own and is not built.

Pure module: no FastAPI.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Optional

from backend.core import frames as frame_files
from backend.core import imageset


def _exported_images(dataset: Path) -> list[Path]:
    images = dataset / "images"
    if not images.is_dir():
        return []
    return sorted(
        (
            f for f in images.rglob("*")
            if f.is_file() and f.suffix.lower() in frame_files.FRAME_SUFFIXES
        ),
        key=lambda f: f.name,
    )


def export_keeps_alpha(dataset: Path) -> Optional[bool]:
    """Whether RS's undistorted export still carries an alpha channel.

    Read from the PNG header of the first exported image — the channel is
    declared there, and one file answers for the export as a whole because RS
    writes them all through the same encoder. None when there is nothing to
    read.
    """
    images = _exported_images(dataset)
    if not images:
        return None
    info = imageset.read_image_info(images[0])
    if info.get("width") is None:
        return None
    return bool(info.get("channels_alpha"))


def frames_carry_alpha(frames_dir: Path) -> bool:
    """Whether step 2 wrote RGBA frames — i.e. whether there is anything to lose."""
    frames = frame_files.list_frames(frames_dir)
    if not frames:
        return False
    picks = sorted({0, len(frames) // 2, len(frames) - 1} & set(range(len(frames))))
    return any(imageset.read_image_info(frames[i])["channels_alpha"] for i in picks)


def audit(project_path: Path, dataset: Path) -> dict[str, Any]:
    """What happened to the alpha between `frames/` and the COLMAP dataset.

    `state` is the whole answer:

    * `no_alpha`    — the frames were never RGBA; nothing to carry, nothing to say
    * `carried`     — the exported images kept the channel; LFS reads it directly
                      ("Using alpha channel as mask source")
    * `dropped`     — RS's export is opaque, so training will see the full frame
    * `unknown`     — there is no export to read yet
    """
    frames_dir = project_path / "frames"
    source_alpha = frames_carry_alpha(frames_dir)
    report: dict[str, Any] = {
        "source_alpha": source_alpha,
        "export_alpha": None,
        "exported_images": 0,
        "state": "no_alpha",
        "note": None,
    }
    if not source_alpha:
        return report

    report["exported_images"] = len(_exported_images(dataset))
    kept = export_keeps_alpha(dataset)
    report["export_alpha"] = kept

    if kept is None:
        report["state"] = "unknown"
        report["note"] = (
            "No COLMAP images to read, so whether the alpha survived cannot be "
            "answered here."
        )
    elif kept:
        report["state"] = "carried"
        report["note"] = (
            "The exported images kept their alpha channel — LichtFeld Studio "
            "reads it as the training mask directly."
        )
    else:
        report["state"] = "dropped"
        report["note"] = (
            "RealityScan's export wrote opaque images, so the alpha did not "
            "survive it. Trying the alpha images step 2 extracted instead."
        )
    return report


def _dimensions(path: Path) -> tuple[Optional[int], Optional[int]]:
    info = imageset.read_image_info(path)
    return info.get("width"), info.get("height")


def deliver_masks(project_path: Path, dataset: Path) -> dict[str, Any]:
    """Copy step 2's alpha images into `<dataset>/masks/`, if they still fit.

    Paired by position: RS exports in the order the images were added, which is
    the sorted input order — the same fallback the coverage check uses when the
    export has renamed everything (§12, 2026-08-20). A *short* export means RS
    dropped frames, and then position means nothing, so this refuses rather
    than pairing a mask with the wrong image.
    """
    masks = frame_files.masks_dir(project_path)
    source = frame_files.list_mask_images(masks)
    exported = _exported_images(dataset)
    report: dict[str, Any] = {
        "available": len(source),
        "written": 0,
        "state": "none",
        "note": None,
    }
    if not source or not exported:
        return report

    if len(source) != len(exported):
        report["state"] = "count_mismatch"
        report["note"] = (
            f"{len(source)} alpha images against {len(exported)} exported ones — "
            "RealityScan did not register every frame, so which mask belongs to "
            "which image is no longer readable. No mask was copied."
        )
        return report

    mask_size = _dimensions(source[0])
    image_size = _dimensions(exported[0])
    if mask_size != image_size and all(image_size) and all(mask_size):
        report["state"] = "geometry_mismatch"
        report["note"] = (
            f"The alpha images are {mask_size[0]}x{mask_size[1]} and the exported "
            f"images {image_size[0]}x{image_size[1]}: RealityScan's undistortion "
            "changed the geometry, so these masks no longer describe these "
            "images. Nothing was copied — LichtFeld Studio would refuse them, "
            "and a mask that is off deletes real surface. Masks in RS's own "
            "geometry have to come from RS itself (Reconstruction Region + "
            "mesh), which this app does not drive yet."
        )
        return report

    target_dir = dataset / "masks"
    target_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for mask, image in zip(source, exported):
        try:
            shutil.copyfile(mask, target_dir / f"{image.stem}.png")
            written += 1
        except OSError:
            continue

    report["written"] = written
    report["state"] = "delivered"
    report["note"] = (
        f"{written} alpha image(s) copied into the dataset's masks/ — the "
        "export dropped the channel, but the geometry still matches, so "
        "LichtFeld Studio reads them from there."
    )
    return report
