import asyncio
import math
import random
import re
import shutil
from pathlib import Path

from backend.core.config import app_config

_STUB_ASSETS = Path(__file__).parents[3] / "tools" / "test_assets"


# ── Real LFS runner ─────────────────────────────────────────────────────────

async def run_lfs_real(project_path: Path, broadcast_fn, settings: dict) -> dict:
    """Calls LichtFeld-Studio.exe in headless/CLI mode."""
    lfs_exe_str = app_config.tools.lfs_exe_path
    if not lfs_exe_str:
        raise FileNotFoundError(
            "lfs_exe_path is not configured.\n"
            "Build LichtFeld Studio from source (C++23 + CUDA 12.8 required),\n"
            "then set lfs_exe_path in Settings, or enable lfs_stub."
        )
    lfs_exe = Path(lfs_exe_str)
    if not lfs_exe.exists():
        raise FileNotFoundError(
            f"LichtFeld-Studio executable not found at: {lfs_exe}\n"
            "Build LichtFeld Studio from source (C++23 + CUDA 12.8 required),\n"
            "then set lfs_exe_path in Settings, or enable lfs_stub."
        )

    rc_output = project_path / "rc_output"
    lfs_output = project_path / "lfs_output"
    lfs_output.mkdir(exist_ok=True)

    iterations = settings.get("iterations", 30000)
    strategy = settings.get("strategy", "default")
    strategy_flag = ["--strategy", "mcmc"] if strategy == "mcmc" else []

    cmd = [
        str(lfs_exe),
        "-d", str(rc_output),
        "-o", str(lfs_output),
        "-i", str(iterations),
        *strategy_flag,
        "--eval",
    ]
    await broadcast_fn("lfs", "INFO", f"[LFS] Launching: {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async for raw_line in proc.stdout:
        line = raw_line.decode("utf-8", errors="replace").strip()
        metrics = _parse_lfs_metrics(line)
        await broadcast_fn(
            "lfs", "INFO", line,
            progress=metrics.get("progress"),
            data=metrics if metrics else None,
        )

    try:
        await asyncio.wait_for(proc.wait(), timeout=1800)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("LichtFeld Studio timed out after 30 minutes")

    if proc.returncode != 0:
        raise RuntimeError(f"LichtFeld Studio exited with code {proc.returncode}")

    await broadcast_fn("lfs", "SUCCESS", "[LFS] Training complete.", progress=1.0)
    return {"lfs_output": str(lfs_output)}


def _parse_lfs_metrics(line: str) -> dict:
    """Parse LichtFeld Studio stdout for training metrics."""
    metrics: dict = {}
    m_iter = re.search(r"iter[ation]*\s+(\d+)\s*/\s*(\d+)", line, re.IGNORECASE)
    if m_iter:
        current, total = int(m_iter.group(1)), int(m_iter.group(2))
        metrics["iteration"] = current
        metrics["progress"] = current / total if total else 0
    m_loss = re.search(r"loss[=:\s]+([0-9.eE+\-]+)", line, re.IGNORECASE)
    if m_loss:
        metrics["loss"] = float(m_loss.group(1))
    m_psnr = re.search(r"psnr[=:\s]+([0-9.]+)", line, re.IGNORECASE)
    if m_psnr:
        metrics["psnr"] = float(m_psnr.group(1))
    m_gauss = re.search(r"gaussian[s]?[=:\s]+([0-9]+)", line, re.IGNORECASE)
    if m_gauss:
        metrics["num_gaussians"] = int(m_gauss.group(1))
    return metrics


# ── Stub LFS runner ─────────────────────────────────────────────────────────

async def run_lfs_stub(project_path: Path, broadcast_fn, settings: dict) -> dict:
    """
    Simulates LichtFeld Studio 3DGS training with realistic metrics.
    Streams progressive log lines + metric data over WebSocket.
    Copies sample.ply to lfs_output/ at completion.
    """
    lfs_output = project_path / "lfs_output"
    lfs_output.mkdir(exist_ok=True)

    duration = app_config.stubs.lfs_stub_duration_seconds
    max_iter = settings.get("iterations", app_config.stubs.lfs_stub_iterations)
    strategy = settings.get("strategy", "default")

    await broadcast_fn(
        "lfs", "INFO",
        "⚠️  [STUB MODE] LichtFeld Studio is simulated — no real exe called.",
        progress=0.0,
    )
    await asyncio.sleep(0.3)

    # --- Startup phase
    startup_lines = [
        "LichtFeld Studio (GPLv3) — C++23/CUDA build",
        f"Loading COLMAP dataset from: {project_path / 'rc_output'}",
        "Found cameras.bin: OK | images.bin: OK | points3D.bin: OK",
        f"Images loaded: {settings.get('frame_count', 120)}",
        f"Sparse points: {random.randint(180000, 320000):,}",
        f"Strategy: {strategy.upper()} | Iterations: {max_iter:,}",
        "CUDA device: NVIDIA GeForce RTX 3080 (10240 MB)",
        "Initializing Gaussians from sparse point cloud...",
        f"Initial Gaussian count: {random.randint(90000, 130000):,}",
        "Starting training...",
    ]
    for line in startup_lines:
        await broadcast_fn("lfs", "INFO", line, progress=0.0)
        await asyncio.sleep(0.3)

    # --- Training simulation
    checkpoint_intervals = [1000, 2000, 5000, 7000, 10000, 15000, 20000, 25000, max_iter]
    checkpoints = sorted({c for c in checkpoint_intervals if c <= max_iter} | {max_iter})

    total_sleep = max(duration - 3.0, 1.0)
    sleep_per_checkpoint = total_sleep / len(checkpoints)

    prev_iter = 0
    for checkpoint_iter in checkpoints:
        await asyncio.sleep(sleep_per_checkpoint)

        t = checkpoint_iter / max_iter  # 0.0 → 1.0

        # Loss: exponential decay toward ~0.018
        loss = 0.35 * math.exp(-3.5 * t) + 0.018 + random.gauss(0, 0.002)
        loss = max(0.012, loss)

        # PSNR: logarithmic growth toward ~28dB
        psnr = 18.0 + 10.0 * math.log10(1 + 8 * t) + random.gauss(0, 0.15)
        psnr = min(32.0, max(16.0, psnr))

        # Gaussians: fast growth then plateau
        if t < 0.4:
            gaussians = int(100_000 + 600_000 * t)
        else:
            gaussians = int(340_000 + 20_000 * math.sin(t * math.pi))
        gaussians += random.randint(-5000, 5000)

        iters_in_block = checkpoint_iter - prev_iter
        iter_per_sec = iters_in_block / sleep_per_checkpoint if sleep_per_checkpoint > 0 else 500

        log_line = (
            f"iter {checkpoint_iter:>6}/{max_iter} | "
            f"loss={loss:.4f} | "
            f"psnr={psnr:.2f}dB | "
            f"gaussians={gaussians:,} | "
            f"speed={iter_per_sec:.0f}it/s"
        )
        metrics_data = {
            "iteration": checkpoint_iter,
            "loss": round(loss, 5),
            "psnr": round(psnr, 3),
            "num_gaussians": gaussians,
            "fps": round(iter_per_sec, 1),
        }

        await broadcast_fn(
            "lfs", "INFO", f"[STUB] {log_line}",
            progress=t,
            data=metrics_data,
        )

        # Densification events early on
        if checkpoint_iter <= 15000 and checkpoint_iter % 5000 == 0:
            await broadcast_fn(
                "lfs", "INFO",
                f"[STUB] Densification step — added ~{random.randint(8000, 15000):,} Gaussians",
                data=metrics_data,
            )

        # Checkpoint save
        if checkpoint_iter in {10000, 20000, max_iter}:
            ckpt_path = lfs_output / f"checkpoint_{checkpoint_iter}.pth"
            ckpt_path.touch()
            await broadcast_fn("lfs", "INFO", f"[STUB] Checkpoint saved → {ckpt_path.name}")

        prev_iter = checkpoint_iter

    # --- Export PLY
    await broadcast_fn("lfs", "INFO", "[STUB] Saving final scene as point_cloud.ply...", progress=0.98)
    await asyncio.sleep(0.5)

    stub_ply = _STUB_ASSETS / "sample.ply"
    output_ply = lfs_output / "point_cloud.ply"
    if stub_ply.exists():
        shutil.copy(stub_ply, output_ply)
    else:
        output_ply.write_bytes(
            b"ply\nformat binary_little_endian 1.0\nelement vertex 0\nend_header\n"
        )

    # Empty .splat for format-detection testing
    (lfs_output / "output.splat").write_bytes(b"")

    final_loss = 0.35 * math.exp(-3.5) + 0.018
    final_psnr = 18.0 + 10.0 * math.log10(9)
    final_gauss = 342_000 + random.randint(-10000, 10000)

    await broadcast_fn(
        "lfs", "SUCCESS",
        f"[STUB] LichtFeld Studio training complete. "
        f"Final: loss={final_loss:.4f} | psnr={final_psnr:.2f}dB | "
        f"gaussians={final_gauss:,} | PLY → {output_ply}",
        progress=1.0,
        data={
            "iteration": max_iter,
            "loss": round(final_loss, 5),
            "psnr": round(final_psnr, 3),
            "num_gaussians": final_gauss,
        },
    )
    return {"lfs_output": str(lfs_output)}


# ── Dispatcher ──────────────────────────────────────────────────────────────

async def run_lfs(project_path: Path, broadcast_fn, settings: dict) -> dict:
    if app_config.stubs.lfs_stub:
        return await run_lfs_stub(project_path, broadcast_fn, settings)
    return await run_lfs_real(project_path, broadcast_fn, settings)
