import asyncio
import random
import shutil
from pathlib import Path

from backend.core.config import app_config

_STUB_ASSETS = Path(__file__).parents[3] / "tools" / "test_assets"


# ── Real RC runner ──────────────────────────────────────────────────────────

async def run_rc_real(project_path: Path, broadcast_fn, settings: dict) -> dict:
    """Calls RealityScan.exe via CLI with the rscmd script."""
    rc_exe_str = app_config.tools.rc_exe_path
    if not rc_exe_str:
        raise FileNotFoundError(
            "rc_exe_path is not configured.\n"
            "Enable rc_stub in Settings, or install RealityCapture via Epic Games Launcher."
        )
    rc_exe = Path(rc_exe_str)
    if not rc_exe.exists():
        raise FileNotFoundError(
            f"RealityScan.exe not found at: {rc_exe}\n"
            "Enable rc_stub in Settings, or install RealityCapture via Epic Games Launcher."
        )

    frames_dir = project_path / "frames"
    rc_output = project_path / "rc_output"
    rc_output.mkdir(exist_ok=True)
    scripts_dir = Path(__file__).parents[2] / "scripts"

    cmd = [
        str(rc_exe),
        "-execrscmd", str(scripts_dir / "rc_align_export.rscmd"),
        str(frames_dir),
        str(rc_output),
        str(scripts_dir),
    ]
    await broadcast_fn("rc", "INFO", f"[RC] Launching: {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async for raw_line in proc.stdout:
        line = raw_line.decode("utf-8", errors="replace").strip()
        await broadcast_fn("rc", _classify_rc_line(line), line)

    try:
        await asyncio.wait_for(proc.wait(), timeout=1800)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("RealityCapture timed out after 30 minutes")

    if proc.returncode != 0:
        raise RuntimeError(f"RealityCapture exited with code {proc.returncode}")

    await broadcast_fn("rc", "SUCCESS", "[RC] Alignment complete.", progress=1.0)
    return {"rc_output": str(rc_output)}


def _classify_rc_line(line: str) -> str:
    ll = line.lower()
    if "error" in ll or "failed" in ll:
        return "ERROR"
    if "warning" in ll:
        return "WARNING"
    if "aligned" in ll or "export" in ll or "done" in ll:
        return "SUCCESS"
    return "INFO"


# ── Stub RC runner ──────────────────────────────────────────────────────────

async def run_rc_stub(project_path: Path, broadcast_fn, settings: dict) -> dict:
    """
    Simulates RealityCapture alignment with realistic progressive log output.
    Copies stub_registration.csv and sample.ply to rc_output/.
    Total duration: app_config.stubs.rc_stub_duration_seconds
    """
    rc_output = project_path / "rc_output"
    rc_output.mkdir(exist_ok=True)
    duration = app_config.stubs.rc_stub_duration_seconds
    frame_count = settings.get("frame_count", 120)

    await broadcast_fn(
        "rc", "INFO",
        "⚠️  [STUB MODE] RealityCapture is simulated — no real exe called.",
        progress=0.0,
    )
    await asyncio.sleep(0.5)

    # --- Phase 1: Loading images (0–15%)
    phase1_lines = [
        "RealityScan 1.5.1 (Build 12345) starting...",
        f"Loading {frame_count} images from input folder...",
        "Parsing EXIF metadata...",
        "Detected lens model: DJI Action Camera (fisheye, focal 4.38mm)",
        f"Grouping images by calibration: 1 group, {frame_count} images",
    ]
    for i, line in enumerate(phase1_lines):
        await broadcast_fn("rc", "INFO", line, progress=(i + 1) / len(phase1_lines) * 0.15)
        await asyncio.sleep(duration * 0.15 / len(phase1_lines))

    # --- Phase 2: Feature detection (15–40%)
    await broadcast_fn("rc", "INFO", "Detecting features (SIFT)...", progress=0.15)
    feature_steps = [
        (0.20, f"Processed {frame_count // 4} / {frame_count} images — features: 142,348"),
        (0.25, f"Processed {frame_count // 2} / {frame_count} images — features: 287,912"),
        (0.30, f"Processed {frame_count * 3 // 4} / {frame_count} images — features: 431,556"),
        (0.38, f"Processed {frame_count} / {frame_count} images — features: 578,204"),
        (0.40, "Feature detection complete. Total keypoints: 578,204"),
    ]
    for prog, line in feature_steps:
        await broadcast_fn("rc", "INFO", line, progress=prog)
        await asyncio.sleep(duration * 0.25 / len(feature_steps))

    # --- Phase 3: Matching (40–65%)
    await broadcast_fn("rc", "INFO", "Computing feature matches (exhaustive)...", progress=0.40)
    match_steps = [
        (0.48, f"Matching pair batch 1/4 — {random.randint(18000, 22000)} inliers"),
        (0.54, f"Matching pair batch 2/4 — {random.randint(16000, 21000)} inliers"),
        (0.59, f"Matching pair batch 3/4 — {random.randint(17000, 20000)} inliers"),
        (0.64, f"Matching pair batch 4/4 — {random.randint(15000, 19000)} inliers"),
        (0.65, "Matching complete. Connected components: 1"),
    ]
    for prog, line in match_steps:
        await broadcast_fn("rc", "INFO", line, progress=prog)
        await asyncio.sleep(duration * 0.25 / len(match_steps))

    # --- Phase 4: Bundle adjustment (65–88%)
    await broadcast_fn("rc", "INFO", "Running bundle adjustment (SfM)...", progress=0.65)
    ba_steps = [
        (0.70, f"Aligned {int(frame_count * 0.6)} / {frame_count} cameras..."),
        (0.75, f"Aligned {int(frame_count * 0.8)} / {frame_count} cameras..."),
        (0.80, f"Aligned {int(frame_count * 0.93)} / {frame_count} cameras..."),
        (0.84, f"Aligned {frame_count - random.randint(0, 3)} / {frame_count} cameras"),
        (0.87, f"Reprojection error: {random.uniform(0.4, 0.7):.3f} px (good)"),
        (0.88, "Bundle adjustment converged."),
    ]
    for prog, line in ba_steps:
        await broadcast_fn("rc", "INFO", line, progress=prog)
        await asyncio.sleep(duration * 0.23 / len(ba_steps))

    # --- Phase 5: Export (88–100%)
    await broadcast_fn("rc", "INFO", "Selecting maximal component...", progress=0.89)
    await asyncio.sleep(duration * 0.04)
    await broadcast_fn("rc", "INFO", "Exporting registration (CSV)...", progress=0.93)

    shutil.copy(
        _STUB_ASSETS / "stub_registration.csv",
        rc_output / "registration.csv",
    )
    await asyncio.sleep(duration * 0.03)
    await broadcast_fn("rc", "INFO", "Exporting sparse point cloud (PLY)...", progress=0.97)
    shutil.copy(
        _STUB_ASSETS / "sample.ply",
        rc_output / "pointcloud.ply",
    )
    await asyncio.sleep(duration * 0.03)

    camera_count = frame_count - random.randint(0, 3)
    point_count = random.randint(180_000, 320_000)
    await broadcast_fn(
        "rc", "SUCCESS",
        f"[STUB] RealityCapture complete. "
        f"Cameras aligned: {camera_count}/{frame_count} | "
        f"Sparse points: {point_count:,} | "
        f"Output: {rc_output}",
        progress=1.0,
    )
    return {"rc_output": str(rc_output), "camera_count": camera_count}


# ── Dispatcher ──────────────────────────────────────────────────────────────

async def run_rc(project_path: Path, broadcast_fn, settings: dict) -> dict:
    if app_config.stubs.rc_stub:
        return await run_rc_stub(project_path, broadcast_fn, settings)
    return await run_rc_real(project_path, broadcast_fn, settings)
