"""Make RealityScan's export readable by LichtFeld Studio.

`-exportRegistration` and `-exportSparsePointCloud` are two exporters that do
not agree with each other, and neither writes quite what the LFS Blender/NeRF
loader expects. Two fixes, both applied to the files RC just wrote:

1. **Intrinsics.** RC writes `camera_model: SIMPLE_RADIAL` and puts fl/cx/cy/w/h
   *inside each frame*, because its undistortion crops every image slightly
   differently. LFS reads the camera model from the top level, does not know
   `SIMPLE_RADIAL`, finds no top-level intrinsics and falls back to
   *equirectangular* - then refuses to train with
   `Use --gut or --undistort to train on cameras with non-pinhole model.`
   while still exiting 0. Hoisting the median intrinsics to the top level and
   naming the model PINHOLE is enough; the per-frame values stay where they are.

2. **Coordinate frame.** The NeRF registration is exported in the NeRF/OpenGL
   convention (Y up, camera looking down -Z) while the sparse cloud is exported
   raw in RC's own frame (Z up). The cloud therefore lands 90 deg off around X
   from the cameras that produced it - visible in the LFS viewer as a scene
   standing upright next to a flat camera path, and fatal for training since
   the Gaussians are initialised in the wrong frame. Rotating the cloud by
   +90 deg around X, `(x, y, z) -> (x, -z, y)`, puts the two back together.

Pure module: no FastAPI, no broadcast. Both functions return a small report the
caller broadcasts.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import numpy as np

# Marker written into the PLY header so a second run does not rotate twice.
_ROTATED_MARKER = "comment 3dgs-pipeline-app: rotated Rx+90 (RC Z-up -> NeRF Y-up)"

_INTRINSIC_KEYS = ("fl_x", "fl_y", "cx", "cy", "camera_angle_x", "camera_angle_y")
_SIZE_KEYS = ("w", "h")
_DISTORTION_KEYS = ("k1", "k2", "k3", "k4", "p1", "p2")

_PLY_TYPES = {
    "char": "i1", "uchar": "u1", "short": "i2", "ushort": "u2",
    "int": "i4", "uint": "u4", "float": "f4", "double": "f8",
    "int8": "i1", "uint8": "u1", "int16": "i2", "uint16": "u2",
    "int32": "i4", "uint32": "u4", "float32": "f4", "float64": "f8",
}


# -- transforms.json ---------------------------------------------------------

def normalise_transforms(rc_output: Path) -> dict:
    """Hoist intrinsics to the top level and localise the image paths.

    Idempotent: running it on an already-normalised file changes nothing.
    """
    path = rc_output / "transforms.json"
    if not path.exists():
        return {"patched": False, "reason": "no transforms.json"}

    data = json.loads(path.read_text(encoding="utf-8"))
    frames = data.get("frames") or []
    if not frames:
        return {"patched": False, "reason": "no frames in transforms.json"}

    def median_of(key: str):
        vals = [f[key] for f in frames if isinstance(f.get(key), (int, float))]
        return statistics.median(vals) if vals else None

    for key in _INTRINSIC_KEYS:
        value = median_of(key)
        if value is not None:
            data[key] = float(value)
    for key in _SIZE_KEYS:
        value = median_of(key)
        if value is not None:
            data[key] = int(round(value))

    # RC exports undistorted images, so the distortion is genuinely zero unless
    # the user changed the export params - only then is OPENCV the honest model.
    distorted = any(
        abs(float(f.get(key, 0) or 0)) > 1e-9
        for f in frames for key in _DISTORTION_KEYS
    )
    data["camera_model"] = "OPENCV" if distorted else "PINHOLE"
    if not distorted:
        for key in ("k1", "k2", "k3", "k4"):
            data.setdefault(key, 0)
    data["is_fisheye"] = bool(data.get("is_fisheye", False))

    # Absolute Windows paths make rc_output unmovable; relative ones do not.
    # Both sides are resolved first: RC writes `G:\...` while the caller may hold
    # a relative or differently-cased path to the same directory.
    root = rc_output.resolve()
    localised = 0
    for frame in frames:
        raw = frame.get("file_path")
        if not raw:
            continue
        candidate = Path(raw.replace("\\", "/"))
        try:
            frame["file_path"] = candidate.resolve().relative_to(root).as_posix()
            localised += 1
        except (ValueError, OSError):
            pass

    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return {
        "patched": True,
        "camera_model": data["camera_model"],
        "frames": len(frames),
        "localised_paths": localised,
        "intrinsics": {
            k: data[k] for k in (*_INTRINSIC_KEYS, *_SIZE_KEYS) if k in data
        },
    }


# -- pointcloud.ply ----------------------------------------------------------

def _read_ply_header(handle) -> tuple[list[str], str, int, list[tuple[str, str]]]:
    """(header_lines, format, vertex_count, [(name, ply_type)]) of the vertex element."""
    lines: list[str] = []
    fmt = "ascii"
    count = 0
    props: list[tuple[str, str]] = []
    in_vertex = False
    while True:
        raw = handle.readline()
        if not raw:
            raise ValueError("truncated PLY header")
        line = raw.decode("ascii", errors="replace").rstrip("\r\n")
        lines.append(line)
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "format":
            fmt = parts[1]
        elif parts[0] == "element":
            in_vertex = parts[1] == "vertex"
            if in_vertex:
                count = int(parts[2])
        elif parts[0] == "property" and in_vertex:
            if parts[1] == "list":
                raise ValueError("list properties are not supported on vertices")
            props.append((parts[2], parts[1]))
        elif parts[0] == "end_header":
            return lines, fmt, count, props


def align_pointcloud_to_cameras(rc_output: Path) -> dict:
    """Rotate the sparse cloud from RC's Z-up frame into the cameras' Y-up one.

    `(x, y, z) -> (x, -z, y)`. Rewrites the file through a temporary copy and
    stamps the header so a re-run is a no-op. Handles ascii and
    binary_little_endian; anything else is left untouched and reported.
    """
    path = rc_output / "pointcloud.ply"
    if not path.exists():
        return {"rotated": False, "reason": "no pointcloud.ply"}

    with open(path, "rb") as handle:
        header, fmt, count, props = _read_ply_header(handle)
        if any(line.startswith(_ROTATED_MARKER) for line in header):
            return {"rotated": False, "reason": "already rotated", "points": count}

        names = [name for name, _ in props]
        missing = [axis for axis in ("x", "y", "z") if axis not in names]
        if missing:
            return {"rotated": False, "reason": f"no {missing} propert(y/ies)"}

        out_header = [*header[:-1], _ROTATED_MARKER, header[-1]]
        tmp = path.with_suffix(".ply.tmp")

        if fmt == "ascii":
            ix, iy, iz = names.index("x"), names.index("y"), names.index("z")
            written = 0
            with open(tmp, "w", encoding="ascii", newline="\n") as out:
                out.write("\n".join(out_header) + "\n")
                for raw in handle:
                    fields = raw.decode("ascii", errors="replace").split()
                    if len(fields) < len(names):
                        continue
                    x, y, z = float(fields[ix]), float(fields[iy]), float(fields[iz])
                    fields[ix], fields[iy], fields[iz] = repr(x), repr(-z), repr(y)
                    out.write(" ".join(fields) + "\n")
                    written += 1
        elif fmt == "binary_little_endian":
            dtype = np.dtype([(name, "<" + _PLY_TYPES[t]) for name, t in props])
            data = np.frombuffer(
                handle.read(count * dtype.itemsize), dtype=dtype
            ).copy()
            y = data["y"].copy()
            data["y"], data["z"] = -data["z"], y
            with open(tmp, "wb") as out:
                out.write(("\n".join(out_header) + "\n").encode("ascii"))
                out.write(data.tobytes())
            written = int(count)
        else:
            return {"rotated": False, "reason": f"unsupported PLY format '{fmt}'"}

    tmp.replace(path)
    return {
        "rotated": True,
        "points": written,
        "rotation": "Rx+90  (x, y, z) -> (x, -z, y)",
    }
