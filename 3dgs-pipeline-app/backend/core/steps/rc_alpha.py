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
own geometry. That route exists now: `step_masks.py` drives it, and
`fit_dataset_masks` below is where its output is checked and made usable.

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
    """Whether RS's undistorted export still carries a *usable* alpha channel.

    The PNG header is not the answer, and reading only the header was a real
    defect. RealityScan's COLMAP exporter writes 4-channel PNGs whatever
    `undistortImagesWicPixlFormat` asks for — `defaults.json` has asked for
    "24-bit BGR" all along and RS ignores it — so the colour-type byte says
    "alpha" on every export it has ever made here, including one whose source
    frames were JPEG and had no alpha at all (publicsemples_truck: 251/251
    exported images RGBA, alpha min 255, max 255, one unique value).

    A constant channel is not a mask. LichtFeld Studio thresholds the alpha at
    0.5, so an all-255 alpha means "keep every pixel" — and it **outranks** the
    mask files rather than deferring to them (`trainer.cpp` logs either
    "Alpha-as-mask enabled" or "Mask file loading enabled", never both). A
    header-only answer therefore reported the alpha "carried" for a dataset
    whose alpha carried nothing, which is how a masked project trains unmasked.

    So the channel is decoded and its content is what answers, over the first,
    middle and last exported image. None when there is nothing to read.
    """
    images = _exported_images(dataset)
    if not images:
        return None
    info = imageset.read_image_info(images[0])
    if info.get("width") is None:
        return None
    if not info.get("channels_alpha"):
        return False

    import cv2  # local: most callers of this module never decode an image

    picks = sorted({0, len(images) // 2, len(images) - 1})
    for index in picks:
        data = cv2.imread(str(images[index]), cv2.IMREAD_UNCHANGED)
        if data is None or data.ndim != 3 or data.shape[2] < 4:
            continue
        alpha = data[:, :, 3]
        # One value over the whole frame is a declared channel with nothing in
        # it; anything else is a real cut-out and worth training against.
        if alpha.min() != alpha.max():
            return True
    return False


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
            "mesh): that is the 'Generate the masks' run of step 3."
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


# ── The other direction: masks RealityScan made itself ──────────────────────

def dataset_mask_images(dataset: Path) -> list[Path]:
    """Every file under `<dataset>/masks/`, sorted by name — the export order."""
    masks = dataset / "masks"
    if not masks.is_dir():
        return []
    return sorted(
        (
            f for f in masks.rglob("*")
            if f.is_file() and f.suffix.lower() in frame_files.FRAME_SUFFIXES
        ),
        key=lambda f: f.name,
    )


def fit_dataset_masks(dataset: Path) -> dict[str, Any]:
    """Make RealityScan's own masks usable by LichtFeld Studio, in place.

    The COLMAP exporter writes `masks/` beside `images/` with the *same*
    basenames and through the *same* undistortion, so the pairing and the
    geometry are right by construction — which is exactly what `deliver_masks`
    above cannot achieve from step 2's source-resolution alpha. Two things are
    still wrong on the way out of RealityScan 2.2, and both are measured, not
    assumed (publicsemple_truck, 251 images):

    * **The masks are half size.** `00000.png` is 973x543 and its mask
      486x271, one for one, over the whole set. Nothing reaches it:
      `mvsPreviewDownscaleFactor=1`, `txtImageDownscaleColor=1` and
      `-calculateHighModel` were each tried and the masks came out at half
      every time, so the resolution belongs to the mask *layer* and not to the
      depth map or the mesh. LichtFeld Studio does not resize — it refuses
      (`Mask '{}' is {}x{} but image '{}' is {}x{}`) — so the app resizes,
      `INTER_NEAREST`, to the exact size of the image beside it.

      **The half is proportional, not absolute**: a 3800 px frame gets a
      1900 px mask, so one mask pixel is always a 2x2 square of image pixels
      and a bigger source does not remove the blocking, it only makes it a
      smaller fraction of the frame. What a bigger source really improves is
      the mesh silhouette underneath it.

      `INTER_NEAREST` is settled rather than a compromise. Diagnosed on
      `masks/00105.png` after a `-calculateHighModel` run: 99 % of its 2x2
      blocks are constant, which is the upscale's own signature, and RS's
      original render recovers exactly as `mask[::2, ::2]`. That render is
      properly anti-aliased — 189 distinct grey levels, and its 4x4 and 8x8
      blocks are *not* constant, so nothing is quantised below half. Redoing
      the upscale with `INTER_LINEAR` is visually indistinguishable and
      LichtFeld Studio thresholds at 0.5 either way
      (`Mask file loading enabled (invert=false, threshold=0.5)`), so the
      filter is not where the sharpness went. The visible staircase is the
      *mesh* outline: flat horizontal runs of the top silhouette measured
      median 2 and p90 7 render pixels.

    * **They are RGBA with an opaque alpha.** So are the exported images —
      RealityScan writes 4-channel PNGs whatever `undistortImagesWicPixlFormat`
      says. Rewriting the masks as single-channel greyscale is what CLAUDE.md
      6.7 already says `masks/` holds, it removes any question about which
      channel is the mask, and it costs a quarter of the bytes.

    Anything that has no image to sit beside is left alone and counted: a mask
    the export renamed or dropped is a fact worth reporting, never a file to
    pair by position — position pairing is what `deliver_masks` refuses for
    the same reason.

    Idempotent: a mask that already matches its image and is already greyscale
    is not rewritten. Never raises.
    """
    report: dict[str, Any] = {
        "masks": 0,
        "images": 0,
        "matched": 0,
        "resized": 0,
        "unmatched": [],
        "size": None,
        "state": "none",
        "note": None,
    }
    masks = dataset_mask_images(dataset)
    images = _exported_images(dataset)
    report["masks"] = len(masks)
    report["images"] = len(images)
    if not masks:
        report["note"] = "RealityScan wrote no masks into the dataset."
        return report

    by_stem = {img.stem: img for img in images}
    import cv2  # local: this module is imported by routes that never resize

    for mask in masks:
        image = by_stem.get(mask.stem)
        if image is None:
            report["unmatched"].append(mask.name)
            continue
        target = _dimensions(image)
        data = cv2.imread(str(mask), cv2.IMREAD_UNCHANGED) if all(target) else None
        if data is None:
            report["unmatched"].append(mask.name)
            continue
        report["matched"] += 1

        needs_resize = _dimensions(mask) != target
        needs_flatten = data.ndim == 3
        if not (needs_resize or needs_flatten):
            continue

        if needs_flatten:
            # RS writes the same value in R, G and B and a constant 255 alpha,
            # so one channel is the mask and the alpha is not.
            data = data[:, :, 0]
        if needs_resize:
            data = cv2.resize(
                data, (target[0], target[1]), interpolation=cv2.INTER_NEAREST
            )
            report["resized"] += 1
        cv2.imwrite(str(mask), data)

    report["size"] = list(_dimensions(masks[0]))
    if report["matched"] == 0:
        report["state"] = "unusable"
        report["note"] = (
            f"{len(masks)} mask(s) were exported but none of them names an "
            f"image in the dataset. LichtFeld Studio pairs masks/<name> with "
            f"images/<name>; nothing here does. The masks were left as they are."
        )
    elif report["unmatched"]:
        report["state"] = "partial"
        report["note"] = (
            f"{report['matched']}/{len(masks)} masks matched an exported image "
            f"({report['resized']} resized to fit). "
            f"{len(report['unmatched'])} did not and were left alone."
        )
    else:
        report["state"] = "ready"
        resized = (
            f", resized from half resolution to {report['size'][0]}x{report['size'][1]}"
            if report["resized"] else ""
        )
        report["note"] = (
            f"{report['matched']} mask(s) in the dataset's masks/, one per "
            f"image, named to match{resized}."
        )
    return report


def inspect_dataset_masks(dataset: Path) -> dict[str, Any]:
    """The same answer as `fit_dataset_masks`, read-only — for the UI.

    Headers only, no decode and no write: this runs on a GET that step 3 calls
    on mount, and the durable answer about a mask run is the dataset itself,
    not a log line the user scrolled past or a page reload threw away.
    """
    report: dict[str, Any] = {
        "masks": 0,
        "images": 0,
        "matched": 0,
        "mismatched": 0,
        "size": None,
        "state": "none",
        "note": None,
    }
    masks = dataset_mask_images(dataset)
    images = _exported_images(dataset)
    report["masks"] = len(masks)
    report["images"] = len(images)
    if not masks:
        report["note"] = "No masks in this dataset."
        return report

    by_stem = {img.stem: img for img in images}
    for mask in masks:
        image = by_stem.get(mask.stem)
        if image is None:
            continue
        if _dimensions(mask) == _dimensions(image):
            report["matched"] += 1
        else:
            report["mismatched"] += 1

    report["size"] = list(_dimensions(masks[0]))
    if report["matched"] == len(images) and not report["mismatched"]:
        report["state"] = "ready"
        report["note"] = (
            f"{report['matched']} masks, one per image, at "
            f"{report['size'][0]}x{report['size'][1]} and up."
        )
    elif report["matched"]:
        report["state"] = "partial"
        report["note"] = (
            f"{report['matched']}/{report['images']} images have a mask that fits"
            + (f", {report['mismatched']} do not" if report["mismatched"] else "")
            + "."
        )
    else:
        report["state"] = "unusable"
        report["note"] = (
            f"{report['masks']} mask(s) here, none of which fits an image of "
            f"this dataset."
        )
    return report
