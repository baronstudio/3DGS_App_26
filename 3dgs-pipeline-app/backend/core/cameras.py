"""Camera poses from the RC registration, for the step 3 viewer overlay.

The sparse cloud alone does not say whether the alignment is any good - the
camera path does. A drone orbit that came back as an orbit is fine; one that
folds back on itself, or breaks into two arcs sitting at different scales, is a
split component you can see instead of read about (CLAUDE.md 7.1).

What cannot be drawn: the frames RC dropped. They are absent from the export
precisely because they have no pose, so a missing frame has no position to plot.
What is drawn instead is the *edge* of each hole - the aligned cameras whose
neighbour in the input order never came back. Those are the bridge frames the
coverage panel talks about, and where the path visibly stops.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

# The RC naming quirks (backslash paths, renamed undistorted exports, the
# name/position/count fallback) are already solved once in the coverage check.
# Importing them keeps one definition instead of two that drift.
from backend.core.steps.step_rc import (
    _basename,
    _input_frame_names,
    _missing_frames,
    _registered_frame_names,
    _sequence_index,
)


def _load(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _pose(matrix: list) -> Optional[tuple[list[float], list[float]]]:
    """(position, row-major 3x3 rotation) from a camera-to-world 4x4."""
    if not isinstance(matrix, list) or len(matrix) < 3:
        return None
    try:
        rows = [[float(v) for v in matrix[r]] for r in range(3)]
    except (TypeError, ValueError, IndexError):
        return None
    if any(len(r) < 4 for r in rows):
        return None
    position = [rows[0][3], rows[1][3], rows[2][3]]
    basis = [rows[0][0], rows[0][1], rows[0][2],
             rows[1][0], rows[1][1], rows[1][2],
             rows[2][0], rows[2][1], rows[2][2]]
    return position, basis


def read_cameras(project_path: Path) -> dict:
    """Poses in export order, tagged with sequence and with the holes around them.

    `transform_matrix` in a NeRF `transforms.json` is camera-to-world in the
    OpenGL frame - which is three.js's frame too, so the matrix goes to the
    viewer untouched. After `rc_postprocess` the point cloud shares it
    (CLAUDE.md 7.2); before it, the cloud would be the thing 90 degrees off,
    not the cameras.
    """
    rc_output = project_path / "rc_output"
    data = _load(rc_output / "transforms.json")
    if not data or not isinstance(data.get("frames"), list):
        return {"available": False, "count": 0, "cameras": []}

    frames = data["frames"]
    cameras: list[dict] = []
    for frame in frames:
        pose = _pose(frame.get("transform_matrix"))
        if pose is None:
            continue
        position, basis = pose
        cameras.append({
            "name": _basename(str(frame.get("file_path", ""))),
            "position": position,
            "basis": basis,
        })

    if not cameras:
        return {"available": False, "count": 0, "cameras": []}

    # How the coverage check managed to line the export up with the input, if at
    # all: RC renames its undistorted copies, so the names often do not match.
    input_names = _input_frame_names(project_path / "frames")
    registered, _ = _registered_frame_names(rc_output)
    missing, missing_count, matched_by = _missing_frames(input_names, registered)
    by_sequence = _sequence_index(project_path)

    for index, camera in enumerate(cameras):
        if matched_by == "name":
            source_name = camera["name"]
        elif matched_by == "position" and index < len(input_names):
            source_name = input_names[index]
        else:
            source_name = None
        camera["source_name"] = source_name
        camera["sequence_id"] = by_sequence.get(source_name) if source_name else None

    gaps_known = matched_by == "name" and bool(missing)
    if gaps_known:
        position_of = {name: i for i, name in enumerate(input_names)}
        for camera in cameras:
            index = position_of.get(camera["source_name"])
            camera["gap_edge"] = index is not None and any(
                0 <= n < len(input_names) and input_names[n] in missing
                for n in (index - 1, index + 1)
            )
    else:
        for camera in cameras:
            camera["gap_edge"] = False

    first = frames[0] if frames else {}
    fov_x = data.get("camera_angle_x") or first.get("camera_angle_x")
    width = data.get("w") or first.get("w")
    height = data.get("h") or first.get("h")

    sequence_ids = sorted({c["sequence_id"] for c in cameras if c["sequence_id"] is not None})
    return {
        "available": True,
        "count": len(cameras),
        "cameras": cameras,
        "matched_by": matched_by,
        "gaps_known": gaps_known,
        "missing_count": missing_count,
        "sequence_ids": sequence_ids,
        "fov_x": float(fov_x) if fov_x else None,
        "aspect": (float(width) / float(height)) if width and height else None,
    }
