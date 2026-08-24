"""Input sources: what sits in `projects/<slug>/input/`, and what it really is.

Step 2 extracts from **one** video — the first `.mp4`, else the first `.mov` —
and only probes it once the job has started, writing `analysis/probe.json`. So
until the first extraction the wizard had nothing to show but a filename and a
byte count, which is not enough to choose an fps policy or a downscale: a 100 fps
4K rush and a 25 fps 1080p one take exactly the same line on screen, and the two
call for opposite settings.

This module answers the question before the run: every file in `input/`, probed,
with a poster frame, and a flag on the one the extraction will actually consume.
`find_extraction_source` is the single definition of that choice — `step_extract`
calls it too, so the badge in the UI cannot drift from the file FFmpeg opens.

Pure module: no FastAPI import, callable from a test on a temp directory (§2.4).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from backend.core.probe import probe_video

VIDEO_SUFFIXES = (".mp4", ".mov")
SUBTITLE_SUFFIXES = (".srt",)

# Thumbnails and probe results live under `preview/`, which §7.3 already defines
# as a cache the app may rebuild at will — a reset deletes it, and that costs one
# ffmpeg call per video.
THUMBS_DIRNAME = "sources"

# Wide enough to read a 16:9 frame at a glance in a list, small enough that a
# handful of them cost less than one extracted frame.
THUMB_WIDTH = 320

_THUMB_TIMEOUT_S = 30


# -- helpers -----------------------------------------------------------------

def _fingerprint(path: Path) -> str:
    """Eight hex digits standing for *this* revision of the file.

    Same convention as `preview.py`: the fingerprint goes in the cached file's
    name, so a re-uploaded video writes a new thumbnail rather than renaming
    over one the browser may still be reading (§12, 2026-08-22).
    """
    stat = path.stat()
    seed = f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}".encode("utf-8")
    return hashlib.blake2b(seed, digest_size=4).hexdigest()


def resolve_ffmpeg(configured: str) -> Optional[str]:
    """The ffmpeg to use for thumbnails, or None when there is none.

    Deliberately does not raise, unlike the extraction step's resolver: a
    missing ffmpeg costs the poster frames, not the panel — the probe falls back
    to an `ffprobe` on PATH on its own, and a list with no thumbnails is still
    the list.
    """
    if configured and Path(configured).exists():
        return configured
    return shutil.which("ffmpeg")


def find_extraction_source(input_dir: Path) -> Optional[Path]:
    """The one video step 2 will extract from: first `.mp4`, else first `.mov`.

    The order is the historical one and it is load-bearing — this is the file
    every existing project's frames came out of. What changes is that the UI now
    reads it from here instead of restating it.
    """
    for suffix in VIDEO_SUFFIXES:
        matches = sorted(
            (f for f in input_dir.glob(f"*{suffix}") if f.is_file()),
            key=lambda f: f.name,
        )
        if matches:
            return matches[0]
    return None


def _kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in VIDEO_SUFFIXES:
        return "video"
    if suffix in SUBTITLE_SUFFIXES:
        return "subtitle"
    return "other"


def _cache_dir(project_path: Path) -> Path:
    return project_path / "preview" / THUMBS_DIRNAME


def _prune_siblings(cache_dir: Path, stem: str, keep: set[str]) -> None:
    """Drop the cached files of earlier revisions of the same source.

    The fingerprint is matched, not merely the prefix: `a.mp4` and `a_b.mp4`
    would otherwise each delete the other's cache on every listing and rebuild
    it on the next one. Best effort — a file the OS still pins costs 20 KB,
    never a failed listing.
    """
    pattern = re.compile(rf"^{re.escape(stem)}_[0-9a-f]{{8}}\.(jpg|json)$")
    try:
        entries = list(cache_dir.iterdir())
    except OSError:
        return
    for path in entries:
        if path.name in keep or not path.is_file():
            continue
        if pattern.match(path.name):
            try:
                os.unlink(path)
            except OSError:
                pass


# -- probe, cached -----------------------------------------------------------

def _read_cached_probe(target: Path) -> Optional[dict[str, Any]]:
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _probe_cached(video: Path, cache_dir: Path, stem: str,
                  ffmpeg_path: str) -> tuple[Optional[dict], Optional[str]]:
    """(probe, error) for one video, memoised on the file's fingerprint.

    ffprobe on a 4K rush is a fifth of a second, and this route is polled by a
    panel that redraws on every settings change — so it is read from disk once
    per revision of the file rather than once per request.
    """
    target = cache_dir / f"{stem}.json"
    cached = _read_cached_probe(target)
    if cached is not None:
        return cached.get("probe"), cached.get("error")

    probe: Optional[dict] = None
    error: Optional[str] = None
    try:
        probe = probe_video(video, ffmpeg_path)
    except Exception as exc:  # noqa: BLE001 — the message is the answer
        error = str(exc)

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"probe": probe, "error": error}, indent=2), encoding="utf-8"
        )
    except OSError:
        pass  # an uncached probe is slow, not wrong

    return probe, error


# -- poster frame ------------------------------------------------------------

def _thumb_seek_s(probe: Optional[dict]) -> float:
    """Where to grab the poster frame.

    Not frame 0: the first frame of a handheld take is very often the operator
    still reaching for the camera, and on a fade-in it is black. A tenth of the
    way in, capped at 2 s so a long rush is not seeked halfway through.
    """
    duration = (probe or {}).get("duration_s")
    if not isinstance(duration, (int, float)) or duration <= 0:
        return 0.0
    return min(2.0, max(0.0, duration * 0.1))


def _build_thumb(video: Path, target: Path, ffmpeg: str, probe: Optional[dict]) -> bool:
    """One JPEG poster frame. Returns whether the file is there afterwards."""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")
    cmd = [
        ffmpeg, "-y", "-v", "error",
        # -ss before -i is the fast seek: FFmpeg jumps to the nearest keyframe
        # instead of decoding everything up to it.
        "-ss", f"{_thumb_seek_s(probe):.3f}",
        "-i", str(video),
        "-frames:v", "1",
        # -2 keeps the height even; the mjpeg encoder writes yuvj420p and
        # refuses an odd side (§6.1, same reason as the extraction scale).
        "-vf", f"scale={THUMB_WIDTH}:-2",
        "-q:v", "4",
        # The output is written to `<name>.jpg.part` and renamed, so the format
        # has to be stated: FFmpeg guesses it from the extension, and `.part` is
        # not one it knows — it answered "Unable to find a suitable output
        # format" and the panel silently had no thumbnails.
        "-f", "image2",
        str(part),
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, timeout=_THUMB_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        part.unlink(missing_ok=True)
        return False

    if completed.returncode != 0 or not part.exists() or part.stat().st_size == 0:
        part.unlink(missing_ok=True)
        return False

    try:
        os.replace(part, target)
    except OSError:
        part.unlink(missing_ok=True)
        return False
    return True


# -- the listing -------------------------------------------------------------

def list_sources(project_path: Path, slug: str, ffmpeg_path: str = "",
                 thumbnails: bool = True) -> dict[str, Any]:
    """Everything `input/` holds, probed, with a poster frame per video.

    Blocking on purpose — ffprobe and ffmpeg are subprocesses. The caller runs
    it in an executor.
    """
    input_dir = project_path / "input"
    ffmpeg = resolve_ffmpeg(ffmpeg_path) if thumbnails else None
    extraction_source = find_extraction_source(input_dir) if input_dir.is_dir() else None

    entries: list[dict[str, Any]] = []
    if not input_dir.is_dir():
        return {
            "sources": entries,
            "extraction_source": None,
            "video_count": 0,
            "ffmpeg_available": bool(ffmpeg),
        }

    cache_dir = _cache_dir(project_path)
    files = sorted(
        (f for f in input_dir.iterdir() if f.is_file()),
        key=lambda f: (_kind(f) != "video", f.name),
    )

    video_count = 0
    for f in files:
        kind = _kind(f)
        if kind == "other":
            continue
        stat = f.stat()
        entry: dict[str, Any] = {
            "filename": f.name,
            "kind": kind,
            "size_bytes": stat.st_size,
            "modified": stat.st_mtime,
            "url": f"/static/{slug}/input/{f.name}",
            "thumb_url": None,
            "probe": None,
            "probe_error": None,
            "is_extraction_source": False,
        }

        if kind == "video":
            video_count += 1
            entry["is_extraction_source"] = (
                extraction_source is not None and f.name == extraction_source.name
            )
            stem = f"{f.stem}_{_fingerprint(f)}"
            probe, error = _probe_cached(f, cache_dir, stem, ffmpeg_path)
            entry["probe"] = probe
            entry["probe_error"] = error

            thumb = cache_dir / f"{stem}.jpg"
            if ffmpeg and (thumb.is_file() or _build_thumb(f, thumb, ffmpeg, probe)):
                entry["thumb_url"] = (
                    f"/static/{slug}/preview/{THUMBS_DIRNAME}/{thumb.name}"
                )
            _prune_siblings(cache_dir, f.stem, {thumb.name, f"{stem}.json"})

        entries.append(entry)

    return {
        "sources": entries,
        "extraction_source": extraction_source.name if extraction_source else None,
        "video_count": video_count,
        "ffmpeg_available": bool(ffmpeg),
    }
