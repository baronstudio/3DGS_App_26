import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path

from backend.core.config import app_config
from backend.core.defaults import ExtractDefaults, load_defaults, resolve_extract_fps
from backend.core.proc import ProcessAborted, kill_tree, release, spawn
from backend.core.project_ops import reset_steps
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


def resolve_ffmpeg_path(configured: str) -> tuple[str, str | None]:
    """The ffmpeg binary to actually run, plus a note when it is not the configured one.

    `probe.py` already falls back to a bare `ffprobe` on PATH when the binary
    next to the configured ffmpeg is missing, so a stale `ffmpeg_path` let the
    probe succeed and killed the step later — on a `Popen` raising WinError 2
    with no filename in the message, i.e. an instant failure with no output at
    all. Both ends resolve the same way now, and a genuinely absent ffmpeg
    fails with the path it looked for (CLAUDE.md §2).
    """
    if configured and Path(configured).exists():
        return configured, None

    found = shutil.which("ffmpeg")
    if found:
        note = (
            f"ffmpeg_path points at a file that does not exist ({configured}) — "
            f"falling back to the ffmpeg on PATH: {found}. "
            "Fix the path in Settings → Tools."
        ) if configured else None
        return found, note

    raise FileNotFoundError(
        f"ffmpeg.exe not found at: {configured or '(not configured)'}\n"
        "No ffmpeg on PATH either. Install FFmpeg and set ffmpeg_path in Settings."
    )


def build_scale_filter(scale_percent: int) -> str | None:
    """The FFmpeg `scale` clause for a percentage of the source resolution.

    Returns None at 100 %, so the untouched extraction adds no filter at all.
    Both dimensions are truncated to an even number: the mjpeg encoder writes
    yuvj420p, whose chroma planes are half-size, and an odd side makes it fail
    outright rather than round for us.
    """
    if scale_percent >= 100:
        return None
    f = scale_percent / 100.0
    return f"scale=trunc(iw*{f:.4f}/2)*2:trunc(ih*{f:.4f}/2)*2"


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
            "scale_percent": extract.scale_percent,
            "max_frames": extract.max_frames,
            "capture_preset": extract.capture_preset,
            "frame_count": frame_count,
        }, indent=2),
        encoding="utf-8",
    )


async def _clear_previous_run(project_path: Path, broadcast_fn) -> None:
    """Wipe what the previous extraction left, before writing the new one.

    FFmpeg overwrites `frame_%04d.jpg` in place, so a second run at a lower fps
    kept the tail of the first one — 300 frames extracted over 500 leaves 200
    orphans that no `scores.json` describes and that the gallery still shows.
    The curation JSON is just as stale: `selection.json` and `scores.json` point
    at frame indices that changed meaning, and `overrides.json` — which is
    otherwise never regenerated (§5) — would apply a manual keep/drop to a
    different picture.

    This is exactly a reset of step 2 (§14.1), so it is the same call: the frame
    set, the analysis and the report go, `input/` never does.
    """
    removed = reset_steps(project_path, [2])
    if removed:
        await broadcast_fn(
            "extract", "INFO",
            f"[extract] Cleared the previous run: {', '.join(removed)}",
            progress=0.0,
        )


async def run_extract(project_path: Path, broadcast_fn, settings: dict) -> dict:
    """FFmpeg frame extraction from the first .mp4/.mov in project_path/input/."""
    input_dir = project_path / "input"
    video_files = list(input_dir.glob("*.mp4")) + list(input_dir.glob("*.mov"))
    if not video_files:
        raise FileNotFoundError(f"No .mp4 or .mov found in {input_dir}")
    input_video = video_files[0]

    # Only once the source is known to exist: a missing video must not cost the
    # frames already on disk.
    await _clear_previous_run(project_path, broadcast_fn)

    frames_dir = project_path / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    extract = resolve_extract_settings(settings)
    quality = extract.quality
    max_frames = extract.max_frames

    ffmpeg_path, ffmpeg_note = resolve_ffmpeg_path(app_config.tools.ffmpeg_path)
    if ffmpeg_note:
        await broadcast_fn("extract", "WARNING", f"[FFmpeg] {ffmpeg_note}")
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

    # Last in the chain on purpose: scaling after the fps gate resizes only the
    # frames that survive it, not every frame of the source.
    scale_clause = build_scale_filter(extract.scale_percent)
    if scale_clause:
        vf_filter += f",{scale_clause}"
        src_w, src_h = probe.get("width"), probe.get("height")
        target = ""
        if src_w and src_h:
            f = extract.scale_percent / 100.0
            target = (
                f" — {src_w}x{src_h} -> "
                f"{int(src_w * f) // 2 * 2}x{int(src_h * f) // 2 * 2}"
            )
        await broadcast_fn(
            "extract", "INFO",
            f"[scale] frames written at {extract.scale_percent}% of the source{target}",
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
