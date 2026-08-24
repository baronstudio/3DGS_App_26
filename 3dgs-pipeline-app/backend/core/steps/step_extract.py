import asyncio
import json
import re
import shutil
from pathlib import Path

from backend.core.config import app_config
from backend.core.defaults import ExtractDefaults, load_defaults, resolve_extract_fps
from backend.core.proc import (
    ProcessAborted,
    iter_lines,
    kill_tree,
    release,
    spawn,
)
from backend.core.project_ops import reset_steps
from backend.core.probe import probe_video
from backend.core.sources import find_extraction_source

# One line of an FFmpeg `-progress` block: a bare lowercase key, then a value
# with no space in it. The value has to be anchored, because FFmpeg's own
# end-of-run summary — `frame=   20 fps=1.2 q=5.0 time=… speed=0.235x` — starts
# with `frame=` too, and it belongs in the log rather than in a progress block.
# Everything else on the pipe (the banner, the stream mapping, an error) is
# logged as it always was.
_PROGRESS_FIELD = re.compile(r"^([a-z0-9_]+)=(\S*)$")

# How often a readable line is written to the LiveLog. The bar itself moves on
# every block (~2/s); repeating that in the log would push everything else out
# of a 500-entry buffer within a minute.
_LOG_EVERY_S = 2.0


def resolve_extract_settings(settings: dict) -> ExtractDefaults:
    """Overlay the per-project settings onto the app defaults.

    Precedence is per-project > defaults > code fallback (CLAUDE.md §4), so only
    the keys the project actually carries are applied. A legacy payload holding a
    bare `fps` is read as an explicit absolute value.

    The block is accepted nested under "extract" or flat, like `rc` and `lfs`:
    nested is what `Project.settings_json` stores and what step 2 now sends, flat
    is what the step was called with before it had a persisted layer.
    """
    base = load_defaults().extract.model_dump()
    incoming = settings or {}
    nested = incoming.get("extract")
    patch_source = nested if isinstance(nested, dict) else incoming
    patch = {k: v for k, v in patch_source.items() if k in base and v is not None}

    if "fps" in patch_source and "fps_mode" not in patch_source:
        patch["fps_mode"] = "absolute"
        patch["fps_absolute"] = float(patch_source["fps"])

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


def _as_int(value: str | None) -> int | None:
    """An FFmpeg progress integer, or None for the `N/A` it writes before it knows."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def out_time_seconds(fields: dict[str, str]) -> float | None:
    """Where in the source FFmpeg has read to, in seconds.

    `out_time_us` is the one to read. `out_time_ms` is deliberately skipped even
    though it is right there: FFmpeg has printed microseconds under that name for
    years — 8.1.1 writes `out_time_us=200000` and `out_time_ms=200000` for the
    same 0.2 s — and a build that ever fixed the misnomer would put the bar out
    by a factor of a thousand. The unambiguous fallback is `out_time` itself,
    `00:01:23.456789`.
    """
    micros = _as_int(fields.get("out_time_us"))
    if micros is not None and micros >= 0:
        return micros / 1_000_000.0

    clock = (fields.get("out_time") or "").strip()
    parts = clock.split(":")
    if len(parts) == 3:
        try:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        except ValueError:
            return None
    return None


def extraction_progress(
    fields: dict[str, str], duration_s: float | None, max_frames: int
) -> float | None:
    """How far the extraction is, from whichever denominator exists.

    Two of them, and the further-along one wins. `out_time` against the source
    duration is the true position — it is smooth, and it holds whatever the fps
    policy resolved to. But `max_frames` ends the run early, so a 200-frame cap
    on a ten-minute source would otherwise crawl to 3 % and stop there.

    Capped just short of 1.0: the store reads progress = 1.0 as "the step is
    done", and the extraction is not done until the frames are counted and
    `extract.json` is written.
    """
    candidates: list[float] = []

    position = out_time_seconds(fields)
    if duration_s and position is not None:
        candidates.append(position / duration_s)

    frame = _as_int(fields.get("frame"))
    if max_frames > 0 and frame is not None:
        candidates.append(frame / max_frames)

    if not candidates:
        return None
    return max(0.0, min(max(candidates), 0.99))


def _progress_summary(fields: dict[str, str], duration_s: float | None) -> str:
    """The readable half of a progress block, for the LiveLog."""
    frame = _as_int(fields.get("frame"))
    position = out_time_seconds(fields)
    bits = [f"{frame} frames" if frame is not None else "starting"]
    if position is not None:
        of = f" / {duration_s:.0f}s" if duration_s else ""
        bits.append(f"{position:.1f}s{of}")
    speed = (fields.get("speed") or "").strip()
    if speed and speed != "N/A":
        bits.append(speed)
    return "[FFmpeg] " + " · ".join(bits)


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
    # Shared with the step 2 panel, which badges this file as the extraction
    # source: two statements of the same rule are two rules waiting to disagree.
    input_video = find_extraction_source(input_dir)
    if input_video is None:
        raise FileNotFoundError(f"No .mp4 or .mov found in {input_dir}")

    extract = resolve_extract_settings(settings)
    quality = extract.quality
    max_frames = extract.max_frames

    ffmpeg_path, ffmpeg_note = resolve_ffmpeg_path(app_config.tools.ffmpeg_path)
    if ffmpeg_note:
        await broadcast_fn("extract", "WARNING", f"[FFmpeg] {ffmpeg_note}")

    # Only once the source *and* the binary are known to exist. The reset used
    # to sit above resolve_ffmpeg_path, which raises when there is no ffmpeg
    # configured and none on PATH - so a misconfigured tool path deleted the
    # frames it was then unable to re-extract. Steps 3 and 4 clear after their
    # exe check for the same reason.
    await _clear_previous_run(project_path, broadcast_fn)

    frames_dir = project_path / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

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
        ffmpeg_path,
        # The only progress channel worth reading. FFmpeg's stderr `frame= …
        # time=` line is redrawn with a bare CR and never terminates, so a
        # readline() regex on it fires once, at exit; `-progress pipe:1` writes
        # newline-delimited `key=value` blocks to stdout instead, and `-nostats`
        # silences the redraw it duplicates.
        "-progress", "pipe:1", "-nostats",
        "-i", str(input_video),
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

    duration_s = probe.get("duration_s")
    if not duration_s and max_frames <= 0:
        await broadcast_fn(
            "extract", "WARNING",
            "[FFmpeg] The source duration is unknown and no frame cap is set — "
            "the extraction bar has no denominator and will stay indeterminate.",
        )

    ffmpeg_output_lines: list[str] = []
    fields: dict[str, str] = {}
    last_log = 0.0

    # One `-progress` block is a run of `key=value` lines closed by
    # `progress=continue` (or `progress=end`); everything else on the pipe is
    # ordinary FFmpeg output. Splitting on CR as well as LF (proc.iter_lines) is
    # what makes the blocks arrive while the run is still going.
    try:
        async for line in iter_lines(proc, loop):
            match = _PROGRESS_FIELD.match(line)
            if not match:
                ffmpeg_output_lines.append(line)
                await broadcast_fn("extract", "INFO", line)
                continue

            key, value = match.group(1), match.group(2).strip()
            fields[key] = value
            if key != "progress":
                continue

            await broadcast_fn(
                "extract", "INFO", "",
                progress=extraction_progress(fields, duration_s, max_frames),
            )

            # The bar moves on every block; the log gets a line every few
            # seconds, so the extraction stays readable next to everything else.
            now = loop.time()
            if now - last_log >= _LOG_EVERY_S:
                last_log = now
                await broadcast_fn(
                    "extract", "INFO", _progress_summary(fields, duration_s)
                )

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
