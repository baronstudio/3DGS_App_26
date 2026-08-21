"""The export-params XML handed to RealityScan's `-exportRegistration`.

`-exportRegistration <file> <config file>` takes an XML describing *which*
exporter to run and with which parameters. RealityScan 2.2 already registers
the one we want, in its own `calibration.xml` next to `RealityScan.exe`:

    <format id="{280B11A4-F9A3-47D1-AE58-C0DEA33487D8}" mask="*.txt"
            descID="9001" desc="COLMAP"
            writer="RealityScan.Export.COLMAP"
            undistortImages="1" exportImages="1" requires="component"/>

The element carries no `<body>`: unlike the CSV/Bundler formats, the COLMAP
template is compiled into the writer. So this module does not describe the
output — it only sets the writer's parameters, whose names are the ones
RealityScan itself uses (`colmapDirStructure`, `colmapFileType`,
`colmapPointFiltering`, `colmapExportMasks`, `colmapMaskExtension`, and the
`undist*` family shared with every other undistorting exporter).

Two things are not preferences and are documented here rather than in the UI:

* **Undistortion cannot be turned off for COLMAP.** RC refuses its own
  `division` distortion model — *"COLMAP does not support the distortion model
  'division' used during alignment. Export with respect to undistorted images
  instead."* — and the camera-model id it would otherwise emit is 13, which is
  not one of COLMAP's twelve. LichtFeld Studio answers that with
  `Invalid camera model ID 13 for image '…'`.
* **The exported world is Y-down.** RC's COLMAP template rotates the scene by
  `(x, y, z) -> (x, -z, y)`, the same `Rx+90` as `rc_postprocess`, which sends
  RC's +Z onto -Y. LFS's *NeRF* loader compensates with its own `Rx+180`; its
  *COLMAP* loader does not, because COLMAP is already the convention it wants.
  So a COLMAP dataset exported as-is trains a splat 180 deg around X away from
  the one `transforms.json` produces today — upside down in the viewer, in
  `export/` and in Blender. `scene_rotate_x` is what puts it back, and it is
  set from `rc.colmap.scene_rotate_x_deg` rather than hardcoded because which
  way is up also depends on the shoot (CLAUDE.md 7.3, "Flip up").

Pure module: no FastAPI, no broadcast.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from backend.core.defaults import ColmapExportDefaults, UndistortDefaults

# calibration.xml, RealityScan 2.2. Identifies the exporter; do not invent one.
COLMAP_FORMAT_ID = "{280B11A4-F9A3-47D1-AE58-C0DEA33487D8}"
COLMAP_WRITER = "RealityScan.Export.COLMAP"

# RealityScan's own tokens, recovered from the executable's string table.
# Only one member of each family appears there literally, so the others are
# the obvious counterparts and are the first thing to check if RC rejects the
# file — see `verify_against_saved_params()` at the bottom.
_DIR_STRUCTURE = {"standard": "CDS_STANDARD", "flat": "CDS_FLAT"}
_FILE_TYPE = {"binary": "CFT_BIN", "ascii": "CFT_TXT"}
_MASK_EXTENSION = {"ext": "CME_EXT", "mask_ext": "CME_MASK_EXT"}
_FIT_MODE = {
    "outer_boundary": "UFM_OUTER",
    "inner_region": "UFM_INNER",
    "in_between": "UFM_BETWEEN",
}
_RESOLUTION_MODE = {
    "preserve": "URM_PRESERVE",
    "custom": "URM_CUSTOM",
    "fit": "URM_FIT",
}
_NAMING = {"sequential": "00000", "original": "$(imageName)"}


def _bool(value: bool) -> str:
    """RC writes its booleans as 1/0 in the format attributes, so match that."""
    return "1" if value else "0"


def _undistort_params(u: UndistortDefaults) -> dict[str, str]:
    return {
        "undistortImages": _bool(u.enabled),
        "exportImages": _bool(u.export_images),
        "undistortPrincipal": _bool(u.undistort_principal_point),
        "undistFitMode": _FIT_MODE[u.fit],
        "undistResMode": _RESOLUTION_MODE[u.resolution],
        "undistortCustomWidth": str(u.custom_width),
        "undistortCustomHeight": str(u.custom_height),
        "undistortDownscaleFactor": str(u.downscale),
        "undistCutOut": f"{u.image_cutout:.6f}",
        "undistMaxPixels": str(u.max_pixels),
        "undistBackColor": u.background_color.lstrip("#").upper(),
        "undistortImagesWicFormat": u.image_format,
        "undistortImagesWicPixlFormat": u.pixel_format,
        "undistortNamingConvention": _NAMING[u.naming_convention],
    }


def _scene_transform_params(rotate_x_deg: float) -> dict[str, str]:
    """The dialog's "Scene transformation" block, identity except around X.

    Emitted in full rather than left out: an absent parameter lets RealityScan
    fall back to whatever the export dialog was last set to by hand, which is
    exactly the kind of state a generated run must not inherit.
    """
    return {
        "MvsExportMoveX": "0.000000",
        "MvsExportMoveY": "0.000000",
        "MvsExportMoveZ": "0.000000",
        "MvsExportRotationX": f"{rotate_x_deg:.6f}",
        "MvsExportRotationY": "0.000000",
        "MvsExportRotationZ": "0.000000",
        "MvsExportScaleX": "1.000000",
        "MvsExportScaleY": "1.000000",
        "MvsExportScaleZ": "1.000000",
    }


def _colmap_params(colmap: ColmapExportDefaults) -> dict[str, str]:
    params = {
        "colmapDirStructure": _DIR_STRUCTURE[colmap.directory_structure],
        "colmapFileType": _FILE_TYPE[colmap.file_type],
        "colmapPointFiltering": _bool(colmap.exclude_unreliable_tie_points),
        "colmapExportMasks": _bool(colmap.export_masks),
        "colmapMaskExtension": _MASK_EXTENSION[colmap.mask_extension],
    }
    params.update(_undistort_params(colmap.undistort))
    params.update(_scene_transform_params(colmap.scene_rotate_x_deg))
    return params


def build_colmap_export_params(colmap: ColmapExportDefaults, dest: Path) -> Path:
    """Write the export-params XML for the COLMAP registration export.

    Generated per run from the settings, for the same reason the `.rscmd` is
    (CLAUDE.md 12): the parameters are user-facing, and a static file would
    have to be hand-edited to change any of them.
    """
    root = ET.Element(
        "format",
        {
            "id": COLMAP_FORMAT_ID,
            "writer": COLMAP_WRITER,
            "mask": "*.txt",
            "requires": "component",
        },
    )
    for name, value in _colmap_params(colmap).items():
        ET.SubElement(root, "parameter", {"variable": name, "value": value})

    dest.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space="  ")
    dest.write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")
    )
    return dest


def verify_against_saved_params(saved: Path) -> dict:
    """Compare our parameter names against an XML saved from RC's export dialog.

    The dialog can write its own settings out, and that file is the only
    authority on the spelling of the enum tokens: RealityScan's string table
    contains `CDS_STANDARD`, `CFT_TXT` and `CME_EXT` but not their
    counterparts, so `CDS_FLAT`, `CFT_BIN` and `CME_MASK_EXT` above are
    inferred. Point this at a saved file to find out which of them are wrong
    before a real run does it the expensive way.

    Returns {"unknown": [...], "missing": [...], "values": {...}} — parameters
    the saved file has and we do not, ones we emit and it does not, and the
    values it uses.
    """
    tree = ET.parse(saved)
    found: dict[str, str] = {}
    for node in tree.iter():
        variable = node.get("variable") or node.get("name")
        if variable:
            found[variable] = node.get("value") or (node.text or "").strip()

    ours = set(_colmap_params(ColmapExportDefaults()))
    return {
        "unknown": sorted(set(found) - ours),
        "missing": sorted(ours - set(found)),
        "values": found,
    }
