import asyncio
import json
import re
import subprocess
from pathlib import Path

from backend.core.config import app_config
from backend.core.defaults import ExtractDefaults, load_defaults, resolve_extract_fps
from backend.core.proc import ProcessAborted, kill_tree, release, spawn
from backend.core.probe import probe_video


def resolve_extract_settings(settings: dict) -> ExtractDefaults:
    """Overlay the per-project settings onto the app defaults.

    Precedence is per-project > defaults > code fallback (CLAUDE.md §4), so only
    the keys the project actually carries are applied. A legacy payload holding a
    bare `fps` is read as an explicit absolute value.
    """
    base = load_defaults().extract.model_dump()
    patch = {k: v for k, v in (settings or {}).items() if k in base and v is not None}

    if "fps" in (settings or {}) and "fps_mode" not in (settings or {}):
        patch["fps_mode"] = "absolute"
        patch["fps_absolute"] = float(settings["fps"])

    return ExtractDefaults.model_validate({**base, **patch})


def _write_extract_meta(
    project_path: Path,
    working_fps: float | None,
    fps_explanation: str,
    input_video: Path | None,
    extract: ExtractDefaults,
    frame_count: int,
) -> None:
    """Record what the extraction actually did, in analysis/extract.json.

    The curation phase needs the resolved working fps to map a cut timecode onto
    an extracted frame index, and needs to know whether mpdecimate broke that
    mapping. Neither belongs in probe.json, which is the raw ffprobe output of
    the source and nothing else.
    """
    analysis_dir = project_path / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (analysis_dir / "extract.json").write_text(
        json.dumps({
            "working_fps": working_fps,
            "fps_explanation": fps_explanation,
            "input_video": str(input_video) if input_video else None,
            "mpdecimate": extract.mpdecimate,
            "quality": extract.quality,
            "max_frames": extract.max_frames,
            "capture_preset": extract.capture_preset,
            "frame_count": frame_count,
        }, indent=2),
        encoding="utf-8",
    )


async def run_extract(project_path: Path, broadcast_fn, settings: dict) -> dict:
    """FFmpeg frame extraction from the first .mp4/.mov in project_path/input/."""
    frames_dir = project_path / "frames"
    frames_dir.mkdir(exist_ok=True)

    input_dir = project_path / "input"
    video_files = list(input_dir.glob("*.mp4")) + list(input_dir.glob("*.mov"))
    if not video_files:
        raise FileNotFoundError(f"No .mp4 or .mov found in {input_dir}")
    input_video = video_files[0]

    extract = resolve_extract_settings(settings)
    quality = extract.quality
    max_frames = extract.max_frames

    ffmpeg_path = app_config.tools.ffmpeg_path or "ffmpeg"
    loop = asyncio.get_running_loop()

    # Probe first: the `auto` fps mode needs the real duration and cadence.
    # A probe failure is not fatal — the resolver falls back to the ratio mode.
    probe: dict = {}
    try:
        probe = await loop.run_in_executor(None, probe_video, input_video, ffmpeg_path)
        analysis_dir = project_path / "analysis"
        analysis_dir.mkdir(exist_ok=True)
        (analysis_dir / "probe.json").write_text(
            json.dumps(probe, indent=2), encoding="utf-8"
        )
        await broadcast_fn(
            "extract", "INFO",
            f"[ffprobe] {probe.get('codec')} {probe.get('width')}x{probe.get('height')} "
            f"@ {probe.get('fps')} fps, {probe.get('duration_s')}s",
        )
    except Exception as e:  # noqa: BLE001 — degraded mode is intended
        await broadcast_fn("extract", "WARNING", f"[ffprobe] unavailable: {e}")

    fps, explanation = resolve_extract_fps(
        extract, probe.get("fps"), probe.get("duration_s")
    )
    await broadcast_fn("extract", "INFO", f"[fps] {explanation}")

    vf_filter = f"fps={fps}"
    if extract.mpdecimate:
        # Kept for users who skip curation entirely. It drops frames
        # non-deterministically, so the frame index no longer maps to a timecode
        # and the curation timeline / scene cuts become unreliable.
        vf_filter += ",mpdecimate"
        await broadcast_fn(
            "extract", "WARNING",
            "mpdecimate is ON — frame indices will not map to timecodes, "
            "which degrades scene detection and the overlap gate.",
        )

    cmd = [
        ffmpeg_path, "-i", str(input_video),
        "-vf", vf_filter,
        "-qscale:v", str(quality),
    ]
    if max_frames > 0:
        cmd += ["-frames:v", str(max_frames)]
    cmd.append(str(frames_dir / "frame_%04d.jpg"))

    await broadcast_fn("extract", "INFO", f"[FFmpeg] Running: {' '.join(cmd)}")

    # Registered so /control abort can kill it from the outside: the reader
    # below blocks in the thread pool and never gets to poll a flag
    # (see core/proc.py).
    proc = spawn(cmd, project_path)

    frame_count = 0
    ffmpeg_output_lines: list[str] = []

    # Stream stdout line-by-line; each readline() blocks in the thread pool.
    try:
        while True:
            raw = await loop.run_in_executor(None, proc.stdout.readline)
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            ffmpeg_output_lines.append(line)
            m = re.search(r"frame=\s*(\d+)", line)
            if m:
                frame_count = int(m.group(1))
                progress = (frame_count / max_frames) if max_frames > 0 else None
                await broadcast_fn("extract", "INFO", line, progress=progress)
            else:
                await broadcast_fn("extract", "INFO", line)

        returncode = await loop.run_in_executor(None, proc.wait)
    except asyncio.CancelledError:
        kill_tree(proc)
        raise
    finally:
        killed = release(project_path, proc)

    if killed:
        raise ProcessAborted("FFmpeg was stopped by the user.")

    if returncode != 0:
        tail = "\n".join(ffmpeg_output_lines[-20:]) if ffmpeg_output_lines else "(no output)"
        raise RuntimeError(
            f"FFmpeg exited with code {returncode}.\nLast output:\n{tail}"
        )

    actual_frames = len(list(frames_dir.glob("frame_*.jpg")))
    _write_extract_meta(
        project_path,
        working_fps=fps,
        fps_explanation=explanation,
        input_video=input_video,
        extract=extract,
        frame_count=actual_frames,
    )
    await broadcast_fn(
        "extract", "SUCCESS",
        f"Extracted {actual_frames} frames → {frames_dir}",
        progress=1.0,
    )
    return {"frame_count": actual_frames, "frames_dir": str(frames_dir)}
