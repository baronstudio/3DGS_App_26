import asyncio
import re
import subprocess
from pathlib import Path

from backend.core.config import app_config
from backend.core.defaults import LFSDefaults, load_defaults
from backend.core.proc import ProcessAborted, kill_tree, release, spawn
from backend.core.steps import colmap_dataset

# Everything the exe prints is wrapped in SGR colour codes; they are noise in
# the LiveLog and they break any level classification done on the text.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# "default" means "whatever this LFS build picks" - v0.5.3 defaults to MRNF.
_STRATEGIES = ("mcmc", "mrnf", "igs+")


# -- Settings resolution -----------------------------------------------------

def resolve_lfs_settings(settings: dict) -> LFSDefaults:
    """Overlay the per-project settings onto the app defaults (CLAUDE.md 4)."""
    base = load_defaults().lfs.model_dump()
    incoming = settings or {}
    nested = incoming.get("lfs")
    patch_source = nested if isinstance(nested, dict) else incoming
    patch = {k: v for k, v in patch_source.items() if k in base and v is not None}
    return LFSDefaults.model_validate({**base, **patch})


def resolve_dataset(project_path: Path) -> dict:
    """Which of step 3's two datasets to train on, and why.

    LichtFeld Studio picks its loader from what it finds under `-d`, and the two
    are not equivalent. The COLMAP export carries **one intrinsic per image**;
    the NeRF `transforms.json` carries one, at the top level, for all of them
    (`Width/height not in transforms.json, reading from first image`). RS
    undistorts every frame to its own size - measured on riverbed_002-v2, frame
    0 is 1523x1129 at fl 729.86 and frame 1 is 1525x1136 at fl 728.25, against a
    hoisted median of 1521x1136 at 721.30 - so on the NeRF path all 300 cameras
    train through intrinsics wrong by a few pixels, each in a different
    direction. The optimiser cannot reconcile the rays and the result is the
    incomplete reconstruction with exploded splat shells.

    Both land in the same world frame, so nothing downstream cares which was
    used: `rc.colmap.scene_rotate_x_deg = 180` composes RS's template rotation
    back to where LFS's NeRF loader would have put it (CLAUDE.md 7.3).

    Returns {"path", "kind": "colmap"|"nerf", "colmap": <inspect report>}.
    """
    dataset, report = colmap_dataset.find_dataset(project_path)
    if report["found"]:
        return {"path": dataset, "kind": "colmap", "colmap": report}
    return {"path": project_path / "rc_output", "kind": "nerf", "colmap": report}


def build_lfs_command(
    lfs_exe: Path, dataset_dir: Path, lfs_output: Path, lfs: LFSDefaults
) -> list[str]:
    """The v0.5.3 command line for one training run.

    Only flags this build actually has - an unknown verb makes the exe exit
    non-zero, so nothing here is invented. The learning rates, the save schedule
    and everything else in `eval/*_optimization_params.json` upstream are
    reachable only through `--config <file.json>`, which this app does not write.
    """
    cmd = [
        str(lfs_exe),
        "--headless",
        "--train",
        "-d", str(dataset_dir),
        "-o", str(lfs_output),
        "-i", str(lfs.iterations),
    ]
    if lfs.strategy in _STRATEGIES:
        cmd += ["--strategy", lfs.strategy]
    # 0 means "leave it to the build", like strategy "default" - the cap is
    # 2 000 000 in v0.5.3 and that is the build's business, not a number worth
    # freezing here.
    if lfs.max_gaussians > 0:
        cmd += ["--max-cap", str(lfs.max_gaussians)]
    if lfs.eval:
        cmd.append("--eval")
        if not lfs.save_eval_images:
            cmd.append("--no-save-eval-images")
    if lfs.background_color:
        cmd += ["--bg-color", lfs.background_color]
    return cmd


# ── LFS runner ──────────────────────────────────────────────────────────────

async def run_lfs(project_path: Path, broadcast_fn, settings: dict) -> dict:
    """Calls LichtFeld-Studio.exe in headless/CLI mode."""
    lfs_exe_str = app_config.tools.lfs_exe_path
    if not lfs_exe_str:
        raise FileNotFoundError(
            "lfs_exe_path is not configured.\n"
            "Build LichtFeld Studio from source (C++23 + CUDA 12.8 required),\n"
            "then set lfs_exe_path in Settings."
        )
    lfs_exe = Path(lfs_exe_str)
    if not lfs_exe.exists():
        raise FileNotFoundError(
            f"LichtFeld-Studio executable not found at: {lfs_exe}\n"
            "Build LichtFeld Studio from source (C++23 + CUDA 12.8 required),\n"
            "then set lfs_exe_path in Settings."
        )

    lfs_output = project_path / "lfs_output"
    lfs_output.mkdir(exist_ok=True)

    dataset = resolve_dataset(project_path)
    report = dataset["colmap"]
    if dataset["kind"] == "colmap":
        await broadcast_fn(
            "lfs", "INFO",
            f"[LFS] Training on the COLMAP dataset "
            f"{Path(dataset['path']).name}/ - {report['cameras']} cameras, "
            f"{report['images']} images, one intrinsic per image.",
        )
    else:
        await broadcast_fn(
            "lfs", "WARNING",
            f"[LFS] No COLMAP dataset in rc_output ({report['reason']}) - "
            f"training on the NeRF transforms.json instead. Its intrinsics are "
            f"a single median for every image, and RealityScan crops each of "
            f"them differently, so expect an incomplete reconstruction. Re-run "
            f"step 3 with the COLMAP export enabled to fix it.",
        )

    lfs = resolve_lfs_settings(settings)
    cmd = build_lfs_command(lfs_exe, Path(dataset["path"]), lfs_output, lfs)
    await broadcast_fn("lfs", "INFO", f"[LFS] Launching: {' '.join(cmd)}")

    loop = asyncio.get_running_loop()

    # Registered so /control abort can kill the tree from the outside: this
    # coroutine spends the whole run parked in the executor and never gets to
    # poll a flag (see core/proc.py).
    proc = spawn(cmd, project_path)

    fatal: str | None = None
    try:
        async for line in _iter_output(proc, loop):
            level = _classify_lfs_line(line)
            if fatal is None:
                fatal = _fatal_reason(line)
            metrics = _parse_lfs_metrics(line)
            await broadcast_fn(
                "lfs", level, line,
                progress=metrics.get("progress"),
                data=metrics if metrics else None,
            )

        returncode = await loop.run_in_executor(None, proc.wait)
    except asyncio.CancelledError:
        # The task died some other way than /control abort (server shutdown,
        # a cancel that beat the kill). Training must not outlive its runner.
        kill_tree(proc)
        raise
    finally:
        killed = release(project_path, proc)

    if killed:
        raise ProcessAborted("LichtFeld Studio was stopped by the user.")

    if returncode != 0:
        raise RuntimeError(f"LichtFeld Studio exited with code {returncode}")

    # v0.5.3 catches its own training exceptions, logs "Training error: ..." and
    # still exits 0 - so the return code alone reports a run that produced
    # nothing as a success. Trust the log and the output instead.
    if fatal:
        raise RuntimeError(f"LichtFeld Studio failed to train: {fatal}")

    splats = sorted(lfs_output.glob("*.ply")) + sorted(lfs_output.glob("*.splat"))
    if not splats:
        raise RuntimeError(
            "LichtFeld Studio exited without writing a splat into "
            f"{lfs_output} - see the log above for the reason."
        )

    await broadcast_fn(
        "lfs", "SUCCESS",
        f"[LFS] Training complete - {splats[-1].name}.",
        progress=1.0,
    )
    return {
        "lfs_output": str(lfs_output),
        "splat": str(splats[-1]),
        "dataset": str(dataset["path"]),
        "dataset_kind": dataset["kind"],
    }


async def _iter_output(proc: subprocess.Popen, loop):
    """Yield clean lines from the child, splitting on CR as well as LF.

    The training progress bar redraws itself with a bare carriage return, so a
    plain readline() swallows the whole run into one multi-megabyte line and the
    UI shows no progress until the exe exits.
    """
    buffer = ""
    while True:
        chunk = await loop.run_in_executor(None, proc.stdout.read1, 4096)
        if not chunk:
            break
        buffer += chunk.decode("utf-8", errors="replace")
        parts = re.split(r"[\r\n]", buffer)
        buffer = parts.pop()
        for part in parts:
            line = _ANSI.sub("", part).strip()
            if line:
                yield line
    line = _ANSI.sub("", buffer).strip()
    if line:
        yield line


def _classify_lfs_line(line: str) -> str:
    """Map the exe's own [info]/[warn]/[error] tag onto a LiveLog level."""
    if "[error]" in line or "[critical]" in line:
        return "ERROR"
    if "[warn]" in line:
        return "WARNING"
    return "INFO"


def _fatal_reason(line: str) -> str | None:
    """The message of a training failure, or None for ordinary output.

    Only the trainer's own abort counts. The `cudaEventDestroy failed: driver
    shutting down` storm that follows every exit is teardown noise from the CUDA
    runtime unloading, not a cause - treating it as fatal would fail every run.
    """
    match = re.search(r"Training error:\s*(.+)$", line)
    return match.group(1).strip() if match else None


def _parse_lfs_metrics(line: str) -> dict:
    """Parse LichtFeld Studio stdout for training metrics."""
    metrics: dict = {}
    # v0.5.3 progress bar: "Training [===>   ] 66% [00m:33s<00m:17s] 300/600"
    m_bar = re.search(r"(\d+)\s*/\s*(\d+)\s*$", line)
    if m_bar and "Training [" in line:
        current, total = int(m_bar.group(1)), int(m_bar.group(2))
        metrics["iteration"] = current
        metrics["progress"] = min(current / total, 1.0) if total else 0
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
    # "Checkpoint saved: ... (2618035 Gaussians, iter 600)" and "loss=… gaussians=…"
    m_gauss = re.search(r"([0-9]+)\s+gaussians\b", line, re.IGNORECASE) \
        or re.search(r"gaussian[s]?[=:\s]+([0-9]+)", line, re.IGNORECASE)
    if m_gauss:
        metrics["num_gaussians"] = int(m_gauss.group(1))
    return metrics
