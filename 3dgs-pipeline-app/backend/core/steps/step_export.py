import shutil
from pathlib import Path


async def run_export(project_path: Path, broadcast_fn, settings: dict) -> dict:
    """
    Collects .ply and .splat files from lfs_output/ and copies them to export/.
    Broadcasts a file_ready event for each file found.
    """
    lfs_output = project_path / "lfs_output"
    export_dir = project_path / "export"
    export_dir.mkdir(exist_ok=True)

    await broadcast_fn(
        "export", "INFO",
        f"Scanning {lfs_output} for output files...",
        progress=0.0,
    )

    ply_files = list(lfs_output.glob("*.ply"))
    splat_files = list(lfs_output.glob("*.splat"))

    if not ply_files and not splat_files:
        raise FileNotFoundError(f"No .ply or .splat files found in {lfs_output}")

    ply_path: str | None = None
    splat_path: str | None = None
    total = len(ply_files) + len(splat_files)
    done = 0

    for ply in ply_files:
        dest = export_dir / ply.name
        shutil.copy2(str(ply), str(dest))
        ply_path = str(dest.resolve())
        done += 1
        await broadcast_fn(
            "export", "INFO",
            f"Copied {ply.name} → export/",
            progress=done / total,
            file=ply_path,
        )

    for splat in splat_files:
        dest = export_dir / splat.name
        shutil.copy2(str(splat), str(dest))
        splat_path = str(dest.resolve())
        done += 1
        await broadcast_fn(
            "export", "INFO",
            f"Copied {splat.name} → export/",
            progress=done / total,
            file=splat_path,
        )

    await broadcast_fn(
        "export", "SUCCESS",
        f"Export complete — {done} file(s) → {export_dir}",
        progress=1.0,
    )
    return {
        "ply_path": ply_path,
        "splat_path": splat_path,
        "export_dir": str(export_dir),
    }
