"""rc_region.py — the Reconstruction Region: RealityScan's `.rsbox`, both ways.

Pure module: no FastAPI, so it stays callable from a test on a temp directory
(CLAUDE.md §2.4).

The region is the volume RealityScan reconstructs inside. It is the input to
the mask route of TODO P4 — a mesh is calculated inside the region and each
camera's view of it becomes that camera's mask — so a region the user placed by
hand is *input*, not an artefact: it lives in `projects/<slug>/region/`, which
no reset deletes (CLAUDE.md §14.1).


What a `.rsbox` really is
-------------------------

Not the shape SESSION 11 guessed. Exported from RealityScan 2.2 on
`fauteuil3d_test` (the samples are in `docs/rs/`):

    <ReconstructionRegion globalCoordinateSystem="NONE" … isGeoreferenced="0"
       isLatLon="0" yawPitchRoll="0 -0 -36.497" widthHeightDepth="42.9 46.3 36.9">
      <Header magic="5395016" version="2"/>
      <CentreEuclid>
        <centre>-7.698 6.147 14.269</centre>
      </CentreEuclid>
      <Residual R="1 0 0 0 1 0 0 0 1" t="0 0 0" s="1" ownerId="{D86E58C1-…}"/>
    </ReconstructionRegion>

Two things a parser has to survive, both observed **inside one run of six
exports**: RS writes `yawPitchRoll` and `widthHeightDepth` as attributes of the
root when the line stays short and as child elements when it does not, and the
centre sits one level down in `<CentreEuclid>` rather than on the root. Hence
the tolerant reader below — attribute or element, `centre` or `center`, and
`.rcbox` accepted on read because that is what RealityCapture wrote.


The rotation, measured rather than assumed
------------------------------------------

`yawPitchRoll` is not (x, y, z) and it is not what its name suggests. Six
throwaway RS runs on the saved `.rsproj` — `-setReconstructionRegionAuto`
followed by `-rotateReconstructionRegion`, which the help documents as rotating
"around its axes", in degrees — pinned it:

    -rotateReconstructionRegion 30  0  0   ->  yawPitchRoll = "0 -30 -0"
    -rotateReconstructionRegion  0 30  0   ->  yawPitchRoll = "-30 -0 -0"
    -rotateReconstructionRegion  0  0 30   ->  yawPitchRoll = "0 -0 -30"

so the first field is a rotation about **Y**, the second about **X**, the third
about **Z**, and all three are stored negated. The composition order was solved
by brute force over the six orderings against three two-axis runs (rotX 40 then
rotY 30; rotY 30 then rotX 40; rotZ 30 then rotX 40), and exactly one candidate
reproduces all of them to floating-point:

    box-to-world  R = Rz(-roll) · Ry(-yaw) · Rx(-pitch)

which is `THREE.Euler(-pitch, -yaw, -roll, 'ZYX')` in the viewer's own terms.
The app therefore stores `euler_deg = (-pitch, -yaw, -roll)` — a plain
`(x, y, z)` triple in the frame the region is expressed in — and converts on
the way in and out. Storing RS's own triple in a file stamped `"frame": "nerf"`
would have been a frame error waiting to be made.


The frame, which is the whole trap
----------------------------------

`-exportReconstructionRegion` writes the region in RealityScan's **native
Z-up** frame — the frame `pointcloud.ply` was in *before* `rc_postprocess`
rotated it by `Rx+90`, `(x, y, z) -> (x, -z, y)` (CLAUDE.md §7.2). The app's
canonical frame is the one on disk after that normalisation, the NeRF one, and
the viewer's own `Rx+180` and its "Flip up" toggle are **display only**
(`viewer/frame.ts`) — neither may reach a file.

Whether `pointcloud.ply` is in the NeRF frame at all depends on
`rc.normalise_for_lfs`, so it is read from the header marker
(`pointcloud_frame`) and never assumed.

None of that is trusted on argument: `coverage()` counts the sparse points
inside the box, and RS's automatic region contains most of the cloud by
construction. The right frame scores ~0.9 and a wrong one scores ~0, which is
why every run logs the number.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable, Optional, Sequence

import numpy as np

from backend.core import ply

# RS's own extension since 2.2; RealityCapture wrote `.rcbox`.
RSBOX_SUFFIXES = (".rsbox", ".rcbox")

# Written verbatim into a file RS has to reload. Both come from the exports in
# docs/rs/ — `magic` is a constant of the format and `version` is 2 in every
# file RealityScan 2.2 produced here.
DEFAULT_MAGIC = "5395016"
DEFAULT_VERSION = "2"

# The frames a region can be expressed in. `rc` is RealityScan's native Z-up
# frame, i.e. what a `.rsbox` holds; `nerf` is the app's canonical one, i.e.
# what `transforms.json` and a normalised `pointcloud.ply` hold.
FRAME_RC = "rc"
FRAME_NERF = "nerf"

# `nerf = Rx(+90) · rc`, the rotation `rc_postprocess.align_pointcloud_to_cameras`
# applies to the sparse cloud. Kept as the two explicit permutations rather than
# a matrix product: they are exact, and this is the one place in the app where
# a sign error is invisible until the mask deletes the subject.
def _rc_to_nerf(x: float, y: float, z: float) -> tuple[float, float, float]:
    return (x, -z, y)


def _nerf_to_rc(x: float, y: float, z: float) -> tuple[float, float, float]:
    return (x, z, -y)


_RX90 = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
_RX90_INV = _RX90.T


# -- Rotations ---------------------------------------------------------------

def _rx(deg: float) -> np.ndarray:
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _ry(deg: float) -> np.ndarray:
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rz(deg: float) -> np.ndarray:
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def euler_to_matrix(euler_deg: Sequence[float]) -> np.ndarray:
    """`(rx, ry, rz)` degrees -> the box-to-world matrix, `Rz · Ry · Rx`.

    Same convention as `THREE.Euler(rx, ry, rz, 'ZYX')`, so the viewer can hand
    the triple straight to the mesh it draws.
    """
    rx, ry, rz = (float(v) for v in euler_deg)
    return _rz(rz) @ _ry(ry) @ _rx(rx)


def matrix_to_euler(matrix: np.ndarray) -> tuple[float, float, float]:
    """The inverse of `euler_to_matrix`, in degrees.

    Gimbal lock (|sin ry| = 1) collapses rx and rz onto one axis; rx is pinned
    at 0 there and the whole rotation is carried by rz, which is the standard
    resolution and is exact — the reconstructed matrix is unchanged.
    """
    m = np.asarray(matrix, dtype=np.float64)
    sy = -m[2, 0]
    sy = max(-1.0, min(1.0, float(sy)))
    ry = math.asin(sy)
    if abs(sy) < 1.0 - 1e-9:
        rx = math.atan2(m[2, 1], m[2, 2])
        rz = math.atan2(m[1, 0], m[0, 0])
    else:
        rx = 0.0
        rz = math.atan2(-m[0, 1], m[1, 1])
    return (math.degrees(rx), math.degrees(ry), math.degrees(rz))


def euler_from_yaw_pitch_roll(ypr: Sequence[float]) -> tuple[float, float, float]:
    """RS's `yawPitchRoll` triple -> the app's `(rx, ry, rz)`."""
    yaw, pitch, roll = (float(v) for v in ypr)
    return (-pitch, -yaw, -roll)


def yaw_pitch_roll_from_euler(euler_deg: Sequence[float]) -> tuple[float, float, float]:
    """The app's `(rx, ry, rz)` -> RS's `yawPitchRoll` triple."""
    rx, ry, rz = (float(v) for v in euler_deg)
    return (-ry, -rx, -rz)


# -- The region ---------------------------------------------------------------

@dataclass(frozen=True)
class Residual:
    """RS's optional rigid+scale correction. Preserved, never invented.

    Identity in every export measured here, which is why nothing composes it
    yet: a non-identity residual would have to be applied to the box before it
    could be drawn, and there is no sample to check that against. `parse_rsbox`
    keeps it so a round-trip is byte-faithful and flags it in `warnings`.
    """
    r: tuple[float, ...] = (1, 0, 0, 0, 1, 0, 0, 0, 1)
    t: tuple[float, float, float] = (0.0, 0.0, 0.0)
    s: float = 1.0
    owner_id: str = ""

    @property
    def is_identity(self) -> bool:
        return (
            np.allclose(self.r, (1, 0, 0, 0, 1, 0, 0, 0, 1), atol=1e-9)
            and np.allclose(self.t, (0, 0, 0), atol=1e-9)
            and abs(self.s - 1.0) < 1e-9
        )


@dataclass(frozen=True)
class Region:
    """An oriented box, in the frame it says it is in."""

    centre: tuple[float, float, float]
    size: tuple[float, float, float]
    euler_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    frame: str = FRAME_NERF
    source: str = "manual"
    residual: Residual = field(default_factory=Residual)
    # Root attributes of the file this came from, so a written box looks to RS
    # like the one it exported. `globalCoordinateSystem` is "NONE" on every
    # non-georeferenced project, but it is not ours to decide.
    attrs: dict[str, str] = field(default_factory=dict)
    magic: str = DEFAULT_MAGIC
    version: str = DEFAULT_VERSION

    @property
    def matrix(self) -> np.ndarray:
        return euler_to_matrix(self.euler_deg)

    def to_dict(self) -> dict:
        return {
            "frame": self.frame,
            "centre": [float(v) for v in self.centre],
            "size": [float(v) for v in self.size],
            "euler_deg": [float(v) for v in self.euler_deg],
            "source": self.source,
        }


def _floats(text: Optional[str], count: int) -> Optional[tuple[float, ...]]:
    if not text:
        return None
    parts = text.replace(",", " ").split()
    if len(parts) < count:
        return None
    try:
        return tuple(float(p) for p in parts[:count])
    except ValueError:
        return None


def _triple(root: ET.Element, name: str) -> Optional[tuple[float, ...]]:
    """A 3-float value RS may have written as an attribute or as a child.

    Both forms come out of the same RealityScan build in the same run — the
    writer spills to elements once the root's attribute line gets long — so
    neither can be treated as the shape.
    """
    got = _floats(root.get(name), 3)
    if got is not None:
        return got
    child = root.find(name)
    if child is not None:
        return _floats(child.text, 3)
    return None


def _find_centre(root: ET.Element) -> Optional[tuple[float, ...]]:
    for path in ("CentreEuclid/centre", "CentreEuclid/center", "centre", "center"):
        node = root.find(path)
        if node is not None:
            got = _floats(node.text, 3)
            if got is not None:
                return got
    return _triple(root, "centre") or _triple(root, "center")


def parse_rsbox(path: Path) -> Optional[Region]:
    """Read a `.rsbox` / `.rcbox` into a Region in RealityScan's native frame.

    None — never an exception — when the file is absent, is not XML, or does
    not carry the three values a box needs: every caller has a fallback, and a
    region that cannot be read is a reason to fit one, not to fail a step.
    """
    if not path or not path.exists():
        return None
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None

    centre = _find_centre(root)
    size = _triple(root, "widthHeightDepth")
    if centre is None or size is None:
        return None
    ypr = _triple(root, "yawPitchRoll") or (0.0, 0.0, 0.0)

    header = root.find("Header")
    residual_node = root.find("Residual")
    residual = Residual()
    if residual_node is not None:
        residual = Residual(
            r=_floats(residual_node.get("R"), 9) or Residual().r,
            t=_floats(residual_node.get("t"), 3) or (0.0, 0.0, 0.0),
            s=float(residual_node.get("s") or 1.0),
            owner_id=residual_node.get("ownerId") or "",
        )

    return Region(
        centre=(centre[0], centre[1], centre[2]),
        size=(abs(size[0]), abs(size[1]), abs(size[2])),
        euler_deg=euler_from_yaw_pitch_roll(ypr),
        frame=FRAME_RC,
        source="rsbox",
        residual=residual,
        attrs={k: v for k, v in root.attrib.items()
               if k not in ("yawPitchRoll", "widthHeightDepth")},
        magic=(header.get("magic") if header is not None else None) or DEFAULT_MAGIC,
        version=(header.get("version") if header is not None else None) or DEFAULT_VERSION,
    )


_DEFAULT_ATTRS = {
    "globalCoordinateSystem": "NONE",
    "globalCoordinateSystemWkt": "NONE",
    "globalCoordinateSystemName": "NONE",
    "isGeoreferenced": "0",
    "isLatLon": "0",
}


def _fmt(value: float) -> str:
    """RS writes ~15 significant digits; anything less loses millimetres."""
    return repr(round(float(value), 12) + 0.0)


def write_rsbox(region: Region, path: Path) -> Path:
    """Write a region as a `.rsbox` RealityScan reloads. Returns `path`.

    The region is converted to RS's native frame first if it is not already in
    it — writing the app's NeRF frame into a file RS reads back is the failure
    this module exists to prevent.

    Values go out as elements rather than attributes: RS writes both shapes and
    accepts both (it reloaded this writer's output byte-identically), and the
    element form is the one that does not depend on how long the line got.
    """
    region = to_rc_frame(region)
    attrs = {**_DEFAULT_ATTRS, **region.attrs}
    yaw, pitch, roll = yaw_pitch_roll_from_euler(region.euler_deg)

    lines = ["<ReconstructionRegion " + " ".join(
        f'{k}="{v}"' for k, v in attrs.items()) + ">"]
    lines.append(f"  <yawPitchRoll>{_fmt(yaw)} {_fmt(pitch)} {_fmt(roll)}</yawPitchRoll>")
    lines.append("  <widthHeightDepth>"
                 f"{_fmt(region.size[0])} {_fmt(region.size[1])} {_fmt(region.size[2])}"
                 "</widthHeightDepth>")
    lines.append(f'  <Header magic="{region.magic}" version="{region.version}"/>')
    lines.append("  <CentreEuclid>")
    lines.append("    <centre>"
                 f"{_fmt(region.centre[0])} {_fmt(region.centre[1])} {_fmt(region.centre[2])}"
                 "</centre>")
    lines.append("  </CentreEuclid>")
    residual = region.residual
    lines.append(
        f'  <Residual R="{" ".join(_fmt(v) for v in residual.r)}"'
        f' t="{" ".join(_fmt(v) for v in residual.t)}"'
        f' s="{_fmt(residual.s)}"'
        + (f' ownerId="{residual.owner_id}"' if residual.owner_id else "")
        + "/>"
    )
    lines.append("</ReconstructionRegion>")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# -- Frames -------------------------------------------------------------------

def to_nerf_frame(points: Iterable[Sequence[float]]) -> list[list[float]]:
    """`Rx+90`, RealityScan's Z-up onto the app's NeRF frame."""
    return [list(_rc_to_nerf(p[0], p[1], p[2])) for p in points]


def to_rc_frame(points_or_region):
    """`Rx-90`, the app's NeRF frame back onto RealityScan's.

    Takes either a Region or a sequence of points — the region conversions are
    the ones every caller wants and a second name for each would be noise.
    """
    if isinstance(points_or_region, Region):
        return _region_to_frame(points_or_region, FRAME_RC)
    return [list(_nerf_to_rc(p[0], p[1], p[2])) for p in points_or_region]


def to_nerf(region: Region) -> Region:
    return _region_to_frame(region, FRAME_NERF)


def _region_to_frame(region: Region, frame: str) -> Region:
    if region.frame == frame:
        return region
    if frame == FRAME_NERF:
        rotation, centre = _RX90, _rc_to_nerf(*region.centre)
    else:
        rotation, centre = _RX90_INV, _nerf_to_rc(*region.centre)
    return replace(
        region,
        centre=centre,
        euler_deg=matrix_to_euler(rotation @ region.matrix),
        frame=frame,
    )


def pointcloud_frame(ply_path: Path) -> str:
    """Which frame `pointcloud.ply` is actually in, read from its header.

    `rc_postprocess` stamps the rotation it applied into the header, and a
    project aligned with `rc.normalise_for_lfs` off carries no stamp and is
    still in RealityScan's own frame. Assuming either way is the bug this
    function exists to prevent.
    """
    try:
        with open(ply_path, "rb") as handle:
            blob = handle.read(4096)
    except OSError:
        return FRAME_NERF
    head = blob.split(b"end_header")[0].decode("ascii", errors="replace")
    return FRAME_NERF if "rotated Rx+90" in head else FRAME_RC


# -- Geometry -----------------------------------------------------------------

_UNIT_CORNERS = np.array([
    [sx, sy, sz]
    for sx in (-0.5, 0.5) for sy in (-0.5, 0.5) for sz in (-0.5, 0.5)
], dtype=np.float64)


def corners(region: Region) -> list[list[float]]:
    """The 8 corners of the oriented box, in the region's own frame.

    Oriented, never min/max: the box carries a rotation, and its axis-aligned
    bounds are the bounds of the *rotated* corners — not of the unrotated ones.
    """
    local = _UNIT_CORNERS * np.asarray(region.size, dtype=np.float64)
    world = local @ region.matrix.T + np.asarray(region.centre, dtype=np.float64)
    return world.tolist()


def _inside_mask(region: Region, points: np.ndarray) -> np.ndarray:
    """Boolean mask of the points inside the box, in the box's own axes."""
    half = np.asarray(region.size, dtype=np.float64) / 2.0
    if np.any(half <= 0):
        return np.zeros(len(points), dtype=bool)
    local = (points - np.asarray(region.centre, dtype=np.float64)) @ region.matrix
    return np.all(np.abs(local) <= half, axis=1)


# A coverage ratio is a statistic; a million points answer it as well as five
# and cost a fifth of the read.
COVERAGE_SAMPLE = 1_000_000


def coverage(region: Region, ply_path: Path,
             max_points: int = COVERAGE_SAMPLE) -> dict:
    """`{"inside", "total", "ratio"}` for the cloud at `ply_path`.

    The one cheap check that the whole frame chain still lines up: RS's
    automatic region contains most of its own sparse cloud by construction, so
    the correct frame scores ~0.9 and a wrong one scores ~0.

    The cloud's frame is read from its header and the *region* is moved onto
    it, never the other way round — the cloud is millions of points and the box
    is eight corners.
    """
    if not ply_path or not ply_path.exists():
        return {"inside": 0, "total": 0, "ratio": None, "reason": "no point cloud"}
    try:
        points = ply.read_xyz(ply_path, max_points)
    except Exception as exc:  # noqa: BLE001 — a coverage number is never fatal
        return {"inside": 0, "total": 0, "ratio": None, "reason": str(exc)}
    if len(points) == 0:
        return {"inside": 0, "total": 0, "ratio": None, "reason": "empty point cloud"}

    here = _region_to_frame(region, pointcloud_frame(ply_path))
    inside = int(_inside_mask(here, points).sum())
    total = int(len(points))
    return {"inside": inside, "total": total, "ratio": inside / total}


def coverage_report(region: Region, ply_path: Path,
                    max_points: int = COVERAGE_SAMPLE) -> dict:
    """Coverage in the cloud's own frame **and** in the wrong one, from one read.

    The second number is the control, and it is the whole point: RS's automatic
    region contains most of its own sparse cloud by construction, so the frame
    the cloud is really in scores ~0.9 and the other does not. One read rather
    than two, because the cloud is up to 142 MB of ASCII.
    """
    frame = pointcloud_frame(ply_path)
    if not ply_path or not ply_path.exists():
        return {"inside": 0, "total": 0, "ratio": None, "reason": "no point cloud",
                "cloud_frame": frame, "by_frame": {}}
    try:
        points = ply.read_xyz(ply_path, max_points)
    except Exception as exc:  # noqa: BLE001 — a coverage number is never fatal
        return {"inside": 0, "total": 0, "ratio": None, "reason": str(exc),
                "cloud_frame": frame, "by_frame": {}}
    if len(points) == 0:
        return {"inside": 0, "total": 0, "ratio": None, "reason": "empty point cloud",
                "cloud_frame": frame, "by_frame": {}}

    total = int(len(points))
    by_frame: dict[str, float] = {}
    for candidate_frame in (FRAME_RC, FRAME_NERF):
        candidate = _region_to_frame(region, candidate_frame)
        by_frame[candidate_frame] = float(_inside_mask(candidate, points).mean())

    inside = int(round(by_frame[frame] * total))
    return {
        "inside": inside,
        "total": total,
        "ratio": by_frame[frame],
        "cloud_frame": frame,
        "by_frame": by_frame,
    }


def region_from_pointcloud(ply_path: Path, percentile: float = 1.0,
                           max_points: int = COVERAGE_SAMPLE) -> Optional[Region]:
    """An axis-aligned seed fitted to the cloud, in the cloud's own frame.

    Percentile bounds, not min/max: one stray point 400 m out otherwise defines
    the whole box, and an RS sparse cloud always has a few. `percentile=1.0`
    trims the outer 1 % from each end of each axis, which is what LichtFeld
    Studio's own crop-box fit defaults to and for the same reason.
    """
    if not ply_path or not ply_path.exists():
        return None
    try:
        points = ply.read_xyz(ply_path, max_points)
    except Exception:  # noqa: BLE001
        return None
    if len(points) == 0:
        return None

    low = np.percentile(points, percentile, axis=0)
    high = np.percentile(points, 100.0 - percentile, axis=0)
    size = np.maximum(high - low, 1e-6)
    centre = (high + low) / 2.0
    return Region(
        centre=tuple(float(v) for v in centre),
        size=tuple(float(v) for v in size),
        euler_deg=(0.0, 0.0, 0.0),
        frame=pointcloud_frame(ply_path),
        source="pointcloud_percentile",
    )


# -- The store: projects/<slug>/region/ ---------------------------------------
#
# Outside `rc_output/` on purpose. A re-alignment is a reset of step 3
# (CLAUDE.md §12, 2026-08-23) and the box the user placed by hand is *input* to
# the mask route, not an artefact of the alignment — losing it to a re-align
# would be losing the only thing in this feature that costs human attention.

REGION_DIRNAME = "region"
REGION_JSON_FILENAME = "region.json"
REGION_RSBOX_FILENAME = "region.rsbox"
REGION_AUTO_FILENAME = "region_auto.rsbox"

SOURCE_RSBOX_AUTO = "rsbox_auto"
SOURCE_MANUAL = "manual"
SOURCE_POINTCLOUD = "pointcloud_percentile"


def region_dir(project_path: Path) -> Path:
    return project_path / REGION_DIRNAME


def sparse_cloud(project_path: Path) -> Path:
    return project_path / "rc_output" / "pointcloud.ply"


def read_region_json(project_path: Path) -> Optional[dict]:
    path = region_dir(project_path) / REGION_JSON_FILENAME
    if not path.exists():
        return None
    try:
        import json
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def region_from_dict(payload: dict) -> Optional[Region]:
    """A Region out of `region.json` (or an API body). None if it is not one."""
    try:
        centre = tuple(float(v) for v in payload["centre"])
        size = tuple(float(v) for v in payload["size"])
    except (KeyError, TypeError, ValueError):
        return None
    if len(centre) != 3 or len(size) != 3:
        return None
    euler = payload.get("euler_deg") or (0.0, 0.0, 0.0)
    try:
        euler = tuple(float(v) for v in euler)[:3]
    except (TypeError, ValueError):
        euler = (0.0, 0.0, 0.0)
    if len(euler) != 3:
        euler = (0.0, 0.0, 0.0)

    provenance = payload.get("rsbox") or {}
    residual_raw = provenance.get("residual") or {}
    residual = Residual(
        r=tuple(residual_raw.get("R") or Residual().r),
        t=tuple(residual_raw.get("t") or (0.0, 0.0, 0.0)),
        s=float(residual_raw.get("s") or 1.0),
        owner_id=str(residual_raw.get("owner_id") or ""),
    )
    return Region(
        centre=centre,
        size=tuple(abs(v) for v in size),
        euler_deg=euler,
        frame=payload.get("frame") or FRAME_NERF,
        source=payload.get("source") or SOURCE_MANUAL,
        residual=residual,
        attrs=dict(provenance.get("attrs") or {}),
        magic=str(provenance.get("magic") or DEFAULT_MAGIC),
        version=str(provenance.get("version") or DEFAULT_VERSION),
    )


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def region_payload(region: Region, cover: Optional[dict] = None) -> dict:
    """`region.json`'s content: the box in the app frame, plus provenance.

    `euler_deg` is `(rx, ry, rz)` degrees applied as `Rz·Ry·Rx` **in the frame
    named by `frame`** — not RS's own `yawPitchRoll`, which is a different
    triple in a different frame and would be a trap in a file stamped "nerf".
    RS's own values are kept under `rsbox` so a round-trip is faithful.
    """
    yaw, pitch, roll = yaw_pitch_roll_from_euler(to_rc_frame(region).euler_deg)
    payload = {
        **region.to_dict(),
        "euler_order": "ZYX",
        "coverage": (cover or {}).get("ratio"),
        "points_inside": (cover or {}).get("inside"),
        "points_total": (cover or {}).get("total"),
        "updated_at": _now(),
        "rsbox": {
            "yaw_pitch_roll": [yaw, pitch, roll],
            "magic": region.magic,
            "version": region.version,
            "attrs": region.attrs,
            "residual": {
                "R": list(region.residual.r),
                "t": list(region.residual.t),
                "s": region.residual.s,
                "owner_id": region.residual.owner_id,
            },
        },
    }
    return payload


def save_region(project_path: Path, region: Region,
                cover: Optional[dict] = None) -> dict:
    """Write `region.json` **and** `region.rsbox`. Returns the payload.

    Both, always: the json is what the UI round-trips and the `.rsbox` is what
    RealityScan reloads, and a project holding one without the other is a
    project where the two disagree.
    """
    import json
    directory = region_dir(project_path)
    directory.mkdir(parents=True, exist_ok=True)
    region = to_nerf(region)
    payload = region_payload(region, cover)
    (directory / REGION_JSON_FILENAME).write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_rsbox(region, directory / REGION_RSBOX_FILENAME)
    return payload


def seed_region(project_path: Path) -> tuple[Optional[Region], str]:
    """The box to start from, and where it came from.

    In order: what RealityScan exported for this alignment, then a percentile
    fit of the sparse cloud. The fallback is a genuinely useful box — it is the
    same one LichtFeld Studio's own crop fit would produce — so it is offered,
    not refused.
    """
    auto = parse_rsbox(region_dir(project_path) / REGION_AUTO_FILENAME)
    if auto is not None:
        return replace(to_nerf(auto), source=SOURCE_RSBOX_AUTO), SOURCE_RSBOX_AUTO
    fitted = region_from_pointcloud(sparse_cloud(project_path))
    if fitted is not None:
        return to_nerf(fitted), SOURCE_POINTCLOUD
    return None, "none"
