import asyncio
import re
from pathlib import Path

from backend.core.config import app_config
from backend.core.defaults import LFSDefaults, load_defaults
from backend.core.project_ops import reset_steps
from backend.core.proc import (
    ProcessAborted,
    iter_lines,
    kill_tree,
    release,
    spawn,
)
from backend.core.steps import colmap_dataset

# "default" means "whatever this LFS build picks" - v0.5.3 defaults to MRNF.
_STRATEGIES = ("mcmc", "mrnf", "igs+")

# What v0.5.3 actually prints, taken from a headless run rather than guessed
# (see _parse_lfs_metrics for the sample lines).
_BAR_ITER = re.compile(r"Training \[.*?\]\s*\d+%\s*\[[^\]]*\]\s*(\d+)\s*/\s*(\d+)")
_BAR_CLOCK = re.compile(r"\[(\d+)m:(\d+)s<(\d+)m:(\d+)s\]")
_SPLATS = re.compile(r"\bSplats:\s*(\d+)")
_FINAL_SPLATS = re.compile(r"\*\s*Final splats:\s*(\d+)")
_LOSS = re.compile(r"\bLoss:\s*([0-9.eE+\-]+)", re.IGNORECASE)
_PSNR = re.compile(r"\bPSNR:\s*([0-9.]+)", re.IGNORECASE)
_EVAL_STEP = re.compile(r"\[Evaluation at step (\d+)\]")
_EVAL_GS = re.compile(r"#GS:\s*(\d+)")
_CHECKPOINT_GS = re.compile(r"\((\d+) Gaussians, iter (\d+)\)")

# Training is 5-95 % of step 4; the rest is loading the dataset and writing the
# splat, neither of which the bar can see.
_TRAIN_FLOOR = 0.05
_TRAIN_CEILING = 0.95


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

    # A re-training is a reset of step 4, exactly as a re-alignment is a reset
    # of step 3 (step_rc) and a re-extraction one of step 2 (step_extract).
    # LichtFeld Studio names its output after the iteration it stopped at -
    # `splat_9000.ply`, `checkpoints/`, `metrics.csv` - and writes into the
    # directory without clearing it, so a shorter second run leaves the previous
    # splat sitting beside the new one. `splats[-1]` below then reports whichever
    # name sorts last, not the one this run produced: after 9 000 iterations,
    # a 4 000-iteration re-run still returns `splat_9000.ply`, and step 5 exports
    # it. Done after the exe is located, so a misconfigured path does not cost
    # the training already on disk.
    removed = reset_steps(project_path, [4])
    if removed:
        await broadcast_fn(
            "lfs", "INFO",
            f"[LFS] Cleared the previous training ({', '.join(removed)}).",
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
        async for line in iter_lines(proc, loop):
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
    """What one line of LichtFeld Studio v0.5.3 output says about the training.

    Measured against a real headless run rather than inferred. The bar is
    redrawn with a bare CR every hundred iterations and reads:

        Training [====>  ] 66% [00m:01s<00m:00s] 100/300 | Loss: 0.1391 | Splats: 281029

    Three things that were wrong before and are why step 4's bar never moved:

    * the previous `(\\d+)\\s*/\\s*(\\d+)\\s*$` anchored the iteration pair to the
      end of the line, and the line ends with the splat count — so it matched
      nothing, and neither did the `iter n/N` alternative, which this build does
      not print;
    * the bar's own percentage is not the training's. On a 300-iteration run it
      read 33 / 66 / 100 % at "Initializing" / 100 / 200, one third per redraw.
      `N/M` after the clock is the only honest number on the line;
    * the gaussian count is written `Splats:`, which no pattern here looked for.

    PSNR is deliberately not sought on the bar: this build prints it only on the
    `[Evaluation at step N]` line an `--eval` run produces.
    """
    metrics: dict = {}

    bar = _BAR_ITER.search(line)
    if bar:
        current, total = int(bar.group(1)), int(bar.group(2))
        metrics["iteration"] = current
        metrics["total_iterations"] = total
        if total:
            # Mapped onto 5-95 %, not 0-100 %. A run spends real time before its
            # first iteration and after its last - 10.3 s of dataset loading and
            # a checkpoint write, on a 300-iteration run - and a bar that sits at
            # 0 through the first and at 100 through the second reports the
            # wrong thing at both ends.
            span = _TRAIN_CEILING - _TRAIN_FLOOR
            metrics["progress"] = _TRAIN_FLOOR + min(current / total, 1.0) * span

        # The clock reads `[elapsed<remaining]`, and only the left half is worth
        # anything: the remaining side is computed from the bar's own broken
        # percentage, so it read `00m:00s` at 100/300 and again at 200/300 on a
        # run with seconds left to go. The bar's ETA in the UI is estimated from
        # the progress samples instead, which is slower to settle and right.
        clock = _BAR_CLOCK.search(line)
        if clock:
            metrics["elapsed_s"] = int(clock.group(1)) * 60 + int(clock.group(2))

    loss = _LOSS.search(line)
    if loss:
        try:
            metrics["loss"] = float(loss.group(1))
        except ValueError:
            pass

    psnr = _PSNR.search(line)
    if psnr:
        metrics["psnr"] = float(psnr.group(1))

    step = _EVAL_STEP.search(line)
    if step:
        metrics["iteration"] = int(step.group(1))

    # Only counts that describe the model itself. The loose "N Gaussians" this
    # used to accept also matched the startup lines - "pre-allocating capacity
    # for 5000000 Gaussians" - which put the build's ceiling in the badge before
    # a single iteration had run.
    for pattern in (_SPLATS, _EVAL_GS, _FINAL_SPLATS, _CHECKPOINT_GS):
        count = pattern.search(line)
        if count:
            metrics["num_gaussians"] = int(count.group(1))
            break

    checkpoint = _CHECKPOINT_GS.search(line)
    if checkpoint:
        metrics.setdefault("iteration", int(checkpoint.group(2)))

    return metrics
