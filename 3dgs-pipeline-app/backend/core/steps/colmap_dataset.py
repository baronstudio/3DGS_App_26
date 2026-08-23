"""Where the COLMAP dataset of step 3 lives, and how to tell it is really there.

Step 3 writes two datasets side by side and step 4 has to pick one of them, so
the layout is described once, here, rather than spelled out at both ends.

**The COLMAP export gets its own subdirectory.** `-exportRegistration` to a NeRF
`transforms.json` writes its own undistorted copies next to the json —
`00000.png`, `00001.png`… — and the COLMAP export, with `directory_structure:
standard`, writes another set under `images/` with *the same names*. Pointed at
a directory holding both, LichtFeld Studio refuses the dataset outright:

    COLMAP dataset contract violation: image '…' is ambiguous under '…':
    multiple files share that basename in subdirectories

which is what a hand-import of `rc_output/` runs into, and why the copy that
trained correctly by hand was `rc_output/` with the top-level PNGs removed. So
the dataset goes in `rc_output/<slug>_COLMAP/` and nothing else does.

What LichtFeld Studio actually looks for is a `cameras`/`images` pair under
`sparse/0/` (or `sparse/`), binary preferred over text — `Missing required
COLMAP metadata pair (cameras.bin/images.bin or cameras.txt/images.txt)` is the
refusal when it is absent. `inspect()` answers the same question before the
trainer is launched, because RealityScan can skip the export without failing
the step: a bad export-params file is `[err:5617]` on stderr and exit code 0,
after which step 4 used to fall back to the NeRF dataset in silence.

Pure module: no FastAPI, no broadcast.
"""

from __future__ import annotations

from pathlib import Path

# JB's own convention, from the manual import that worked: one folder per
# project, named after it, so several exports are never confused for one.
COLMAP_DIR_SUFFIX = "_COLMAP"

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def colmap_dataset_dir(project_path: Path) -> Path:
    """`rc_output/<slug>_COLMAP` — where step 3 asks RS to write the dataset."""
    return project_path / "rc_output" / f"{project_path.name}{COLMAP_DIR_SUFFIX}"


def find_dataset(project_path: Path) -> tuple[Path, dict]:
    """The dataset to train on, and what is in it.

    The expected name first, then any other `*_COLMAP` in `rc_output/`: a
    project copied under a new name keeps the directory the *old* one wrote
    (`project_ops.copy` duplicates the tree verbatim), and matching on the slug
    alone would answer "no COLMAP dataset" for a project that has a perfectly
    good one. Returns the expected path with its failure report when nothing
    valid is found, so the caller always has something to name.
    """
    expected = colmap_dataset_dir(project_path)
    report = inspect(expected)
    if report["found"]:
        return expected, report

    rc_output = project_path / "rc_output"
    if rc_output.is_dir():
        for candidate in sorted(rc_output.glob(f"*{COLMAP_DIR_SUFFIX}")):
            if candidate == expected or not candidate.is_dir():
                continue
            other = inspect(candidate)
            if other["found"]:
                return candidate, other

    return expected, report


def sparse_model_dir(dataset: Path) -> tuple[Path | None, str | None]:
    """The `sparse/0` (or `sparse`) holding a cameras/images pair, and its type.

    Returns (path, "binary"|"ascii") or (None, None). Binary wins when both are
    present, which is LFS's own order ("Found both binary and text COLMAP
    files. Prioritizing binary files.").
    """
    for candidate in (dataset / "sparse" / "0", dataset / "sparse"):
        for ext, kind in (("bin", "binary"), ("txt", "ascii")):
            if (candidate / f"cameras.{ext}").exists() and (
                candidate / f"images.{ext}"
            ).exists():
                return candidate, kind
    return None, None


def _camera_count(sparse: Path, file_type: str) -> int:
    """How many intrinsics the export carries — the whole point of this route.

    One per image is what makes COLMAP worth the detour: RS crops every
    undistorted image differently, so a single hoisted median (the NeRF path)
    describes none of them. A count of 1 means the export happened but collapsed
    the calibration, which is worth seeing.
    """
    try:
        if file_type == "ascii":
            with open(sparse / "cameras.txt", encoding="utf-8", errors="replace") as fh:
                return sum(1 for line in fh if line.strip() and not line.startswith("#"))
        # COLMAP's binary cameras file opens with a uint64 count.
        return int.from_bytes((sparse / "cameras.bin").read_bytes()[:8], "little")
    except (OSError, ValueError):
        return 0


def _image_count(dataset: Path) -> int:
    images = dataset / "images"
    if not images.is_dir():
        return 0
    return sum(
        1 for f in images.rglob("*")
        if f.is_file() and f.suffix.lower() in _IMAGE_SUFFIXES
    )


def inspect(dataset: Path) -> dict:
    """Is this a dataset LichtFeld Studio will accept, and what is in it?

    Never raises — this runs on the happy path of both steps 3 and 4, and a
    directory it cannot read is a `found: False` with a reason, not an
    exception on top of an otherwise good alignment.
    """
    report = {
        "path": str(dataset),
        "found": False,
        "reason": None,
        "sparse": None,
        "file_type": None,
        "cameras": 0,
        "images": 0,
        "points3d": False,
    }
    if not dataset.is_dir():
        report["reason"] = "no such directory"
        return report

    sparse, file_type = sparse_model_dir(dataset)
    if sparse is None:
        report["reason"] = (
            "no cameras/images pair under sparse/0 - RealityScan did not write "
            "the COLMAP model"
        )
        return report

    report["sparse"] = str(sparse)
    report["file_type"] = file_type
    report["cameras"] = _camera_count(sparse, file_type)
    report["images"] = _image_count(dataset)
    report["points3d"] = any(
        (sparse / f"points3D.{ext}").exists() for ext in ("bin", "txt")
    )

    if report["images"] == 0:
        report["reason"] = "sparse/ was written but images/ is empty"
        return report

    report["found"] = True
    return report
