"""
scenes.py — cut detection. Each cut splits the footage into a *sequence*.

Sequences matter downstream: the sharpness median must not straddle a cut, the
overlap gate resets at every cut, and RealityScan should import each sequence as
its own image group (CLAUDE.md §7).

Two paths, in order of preference:

  1. PySceneDetect `AdaptiveDetector` on the **source video**, then the cut
     timecodes are mapped onto extracted frame indices via the working fps.
     This is the accurate one — it sees every source frame, not one in five.
  2. An HSV-histogram fallback over the **extracted frames**, used whenever the
     source video is gone, unreadable, or mpdecimate has broken the
     frame-index <-> timecode mapping the first path depends on.

Both return the same thing: the frame indices that *start* a new sequence.
"""

import math
from pathlib import Path
from typing import Callable, Optional, Sequence

import cv2
import numpy as np

# Frames the fallback compares at; cut detection needs colour layout, not detail.
FALLBACK_MAX_DIM = 320

# A cut must clear both bars: be a local outlier *and* a large absolute change.
#
# The relative bar alone over-fires badly. Measured on two real continuous
# shots (a 212-frame drone orbit and a 148-frame walkthrough), median + 6*MAD
# reported 13 and 4 cuts where PySceneDetect on the source found none — at one
# frame every 0.5 s the camera has simply moved a lot between samples.
#
# The absolute bar is safe here in a way an absolute *sharpness* threshold never
# is: histogram correlation is already normalised to [0, 1] and independent of
# content scale. Those same continuous shots peak at 0.46, while a hard cut
# between two different scenes lands at 0.8+.
#
# The error is asymmetric, so both bars lean conservative: a missed cut costs a
# slightly wide sharpness window and one un-reset overlap reference, whereas an
# invented cut resets the gate mid-shot and forces a redundant frame to be kept.
FALLBACK_RELATIVE_K = 8.0
FALLBACK_MIN_DELTA = 0.6


def sequence_ids(frame_count: int, boundaries: Sequence[int]) -> list[int]:
    """Expand sequence-start indices into one sequence id per frame."""
    starts = sorted({b for b in boundaries if 0 <= b < frame_count} | {0})
    ids = [0] * frame_count
    current = -1
    next_start = 0
    for i in range(frame_count):
        if next_start < len(starts) and i == starts[next_start]:
            current += 1
            next_start += 1
        ids[i] = max(current, 0)
    return ids


def detect_from_video(
    video_path: Path,
    frame_count: int,
    working_fps: float,
    detector: str = "adaptive",
    min_scene_len_frames: int = 15,
) -> list[int]:
    """Cut indices from the source video, expressed in extracted-frame numbers.

    `working_fps` is the fps FFmpeg actually sampled at, so extracted frame i
    sits at t = i / working_fps in the source. Raises on any failure — the
    caller falls back to `detect_from_frames`.
    """
    from scenedetect import AdaptiveDetector, ContentDetector, detect

    if working_fps <= 0:
        raise ValueError("working_fps must be > 0 to map cuts onto frame indices")

    # min_scene_len is expressed in *extracted* frames by the settings; convert
    # to seconds, which PySceneDetect accepts directly as a float.
    min_len_s = max(0.1, min_scene_len_frames / working_fps)

    det = (
        ContentDetector(min_scene_len=min_len_s)
        if detector == "content"
        else AdaptiveDetector(min_scene_len=min_len_s)
    )
    scene_list = detect(str(video_path), det)

    boundaries: list[int] = [0]
    for start_tc, _end_tc in scene_list:
        idx = math.floor(start_tc.get_seconds() * working_fps)
        if 0 < idx < frame_count:
            boundaries.append(idx)
    return sorted(set(boundaries))


def _hsv_histogram(path: Path, max_dim: int = FALLBACK_MAX_DIM) -> Optional[np.ndarray]:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest > max_dim:
        scale = max_dim / longest
        img = cv2.resize(
            img, (max(1, round(w * scale)), max(1, round(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist.flatten()


def detect_from_frames(
    paths: Sequence[Path],
    min_scene_len_frames: int = 15,
    relative_k: float = FALLBACK_RELATIVE_K,
    min_delta: float = FALLBACK_MIN_DELTA,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> list[int]:
    """Fallback cut detection over the extracted frames themselves.

    Adaptive in the same spirit as PySceneDetect's detector: a frame is a cut
    when its histogram distance from the previous frame stands out against the
    local median distance, rather than against a fixed threshold. Extracted
    frames are seconds apart, so absolute distances are meaningless here.
    """
    n = len(paths)
    if n < 2:
        return [0]

    deltas: list[float] = [0.0]
    prev = _hsv_histogram(paths[0])
    for i in range(1, n):
        cur = _hsv_histogram(paths[i])
        if prev is None or cur is None:
            deltas.append(0.0)
        else:
            # Correlation is 1.0 for identical histograms; use its complement.
            corr = float(cv2.compareHist(prev, cur, cv2.HISTCMP_CORREL))
            deltas.append(max(0.0, 1.0 - corr))
        prev = cur if cur is not None else prev
        if progress_cb is not None:
            progress_cb(i + 1, n)

    arr = np.asarray(deltas[1:], dtype=float)
    if arr.size == 0:
        return [0]
    median = float(np.median(arr))
    # Median absolute deviation — robust to the handful of real cuts we hunt for.
    mad = float(np.median(np.abs(arr - median))) or 1e-6
    threshold = max(median + relative_k * mad, min_delta)

    boundaries = [0]
    for i in range(1, n):
        if deltas[i] > threshold and (i - boundaries[-1]) >= min_scene_len_frames:
            boundaries.append(i)
    return boundaries


def detect_sequences(
    paths: Sequence[Path],
    video_path: Optional[Path],
    working_fps: Optional[float],
    detector: str = "adaptive",
    min_scene_len_frames: int = 15,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> tuple[list[int], str]:
    """Resolve one sequence id per frame. Returns (ids, method_used)."""
    n = len(paths)
    if n == 0:
        return [], "empty"

    if detector == "off":
        return [0] * n, "off (single sequence)"

    if video_path is not None and video_path.exists() and working_fps:
        try:
            boundaries = detect_from_video(
                video_path, n, working_fps, detector, min_scene_len_frames
            )
            return sequence_ids(n, boundaries), f"PySceneDetect {detector} on source video"
        except Exception:  # noqa: BLE001 — the fallback is the whole point
            pass

    boundaries = detect_from_frames(paths, min_scene_len_frames, progress_cb=progress_cb)
    return sequence_ids(n, boundaries), "histogram fallback on extracted frames"


def sequence_spans(ids: Sequence[int]) -> list[dict]:
    """Compact [{id, start_index, end_index, frame_count}] view of the ids."""
    spans: list[dict] = []
    for i, sid in enumerate(ids):
        if not spans or spans[-1]["id"] != sid:
            spans.append({"id": sid, "start_index": i, "end_index": i, "frame_count": 0})
        spans[-1]["end_index"] = i
        spans[-1]["frame_count"] += 1
    return spans
