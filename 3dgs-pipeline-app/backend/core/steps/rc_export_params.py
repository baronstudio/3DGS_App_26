r"""The export-params XML handed to RealityScan's `-exportRegistration`.

`-exportRegistration <file> <config file>` takes a *settings* file, the one the
Export Registration dialog writes — not a format definition. The two look
nothing alike, and confusing them is what made RealityScan answer

    Loading of the configuration from the file 'colmap_export_params.xml'
    failed. [err:5617]

and then hold the whole batch open on a modal, so the step never returned.

A **format definition** lives in `calibration.xml` next to `RealityScan.exe`
and declares which writer produces which file type. RealityScan 2.2 already
registers the one we want:

    <format id="{280B11A4-F9A3-47D1-AE58-C0DEA33487D8}" mask="*.txt"
            descID="9001" desc="COLMAP"
            writer="RealityScan.Export.COLMAP"
            undistortImages="1" exportImages="1" requires="component"/>

A **settings file** is what the CLI reads, and its shape is the one every
RealityScan tool that can save its settings uses — see the three files shipped
under `Settings/SimplifiedExport/` (`simplify.xml`, `smooth.xml`,
`reprojectTexture.xml`, matching exactly the three commands the help documents
as "you can export these settings from the tool"):

    <Configuration id="{GUID}">
      <entry key="variable" value="…"/>
    </Configuration>

`Configuration\entry` is also the only XPath-shaped literal in the executable.
Measured against RealityScan 2.2 with a probe batch: the `<format>` shape fails
to load (err:5617); this one loads and proceeds to the export itself.

The `id` is the format GUID. It is not checked when the configuration is read —
a wrong GUID and no GUID at all both load — but it is the only thing that can
say *which* exporter to run: `calibration.xml` gives the `*.txt` mask to both
COLMAP and Boujou, so the output path cannot disambiguate them.

The keys are RealityScan's own, recovered from the executable's string table
where they sit together under a `CalibrationExportSettings\` prefix: `colmap*`
for the format's own options, `exportUndistorted` / `undist*` for the
undistortion block shared with every undistorting exporter, and `MvsExport*`
for the scene transformation. **Values are not validated when the file is
loaded** — a misspelt enum token is ignored rather than refused, so a wrong one
shows up as an output that does not match the request (ASCII instead of binary,
one resolution for every image instead of per-image) and never as an error.
`verify_against_saved_params()` at the bottom is how to settle them against a
file saved from the dialog.

Two things are not preferences and are documented here rather than in the UI:

* **Undistortion cannot be turned off for COLMAP.** RS refuses its own
  `division` distortion model — *"COLMAP does not support the distortion model
  'division' used during alignment. Export with respect to undistorted images
  instead."* — and the camera-model id it would otherwise emit is 13, which is
  not one of COLMAP's twelve. LichtFeld Studio answers that with
  `Invalid camera model ID 13 for image '…'`.
* **The exported world is Y-down.** RS's COLMAP template rotates the scene by
  `(x, y, z) -> (x, -z, y)`, the same `Rx+90` as `rc_postprocess`, which sends
  RS's +Z onto -Y. LFS's *NeRF* loader compensates with its own `Rx+180`; its
  *COLMAP* loader does not, because COLMAP is already the convention it wants.
  So a COLMAP dataset exported as-is trains a splat 180 deg around X away from
  the one `transforms.json` produces today — upside down in the viewer, in
  `export/` and in Blender. `scene_rotate_x_deg` is what puts it back, and it
  is a setting rather than a constant because which way is up also depends on
  the shoot (CLAUDE.md 7.3, "Flip up").

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
# the obvious counterparts and are the first thing to check when the export
# comes out unlike what was asked for — see `verify_against_saved_params()`.
_DIR_STRUCTURE = {"standard": "CDS_STANDARD", "flat": "CDS_FLAT"}
# `CFT_BIN` is known to be wrong and kept only so the mapping stays complete:
# asking for it produced a *text* model on RealityScan 2.2. Every file of the
# install was searched for a `CFT_`/`CDS_`/`CME_` token and the only three that
# exist are `CFT_TXT`, `CDS_STANDARD` and `CME_EXT` - the three defaults, which
# sit consecutively in the string table right after their key names. The
# counterparts are not in the binary at all, so the real spelling cannot be
# recovered from it; `defaults.json` therefore asks for ascii, which is what RS
# writes either way, and `step_rc.check_colmap_export` reports the mismatch if
# anything asks for binary.
_FILE_TYPE = {"binary": "CFT_BIN", "ascii": "CFT_TXT"}
_MASK_EXTENSION = {"ext": "CME_EXT", "mask_ext": "CME_MASK_EXT"}
# No UFM_/URM_ tokens exist in the string table, unlike the colmap* families:
# these two are plain combo-box indices, in the order the dialog lists them.
_FIT_MODE = {"outer_boundary": 0, "inner_region": 1, "in_between": 2}
_RESOLUTION_MODE = {"preserve": 0, "custom": 1, "fit": 2}
_NAMING = {"sequential": "00000", "original": "$(imageName)"}


def _bool(value: bool) -> str:
    """RealityScan writes its booleans as 1/0, so match that."""
    return "1" if value else "0"


def _undistort_params(u: UndistortDefaults) -> dict[str, str]:
    return {
        "exportUndistorted": _bool(u.enabled),
        "exportImages": _bool(u.export_images),
        "undistPrincipalMode": _bool(u.undistort_principal_point),
        "undistFitMode": str(_FIT_MODE[u.fit]),
        "undistResMode": str(_RESOLUTION_MODE[u.resolution]),
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
    root = ET.Element("Configuration", {"id": COLMAP_FORMAT_ID})
    for name, value in _colmap_params(colmap).items():
        ET.SubElement(root, "entry", {"key": name, "value": value})

    dest.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space="  ")
    dest.write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")
    )
    return dest


def build_mask_export_params(colmap: ColmapExportDefaults, dest: Path) -> Path:
    """The same export, with `colmapExportMasks` on — the mask run's params.

    There is deliberately no `rc_mask_params.py` and no second key family. The
    masks RealityScan makes from the mesh are exported *by the COLMAP writer*,
    which means they come out of the same `undist*` block as `images/`, cropped
    the same way and named the same way, in `masks/` beside them. That is what
    removes both of TODO P4's stated risks — the geometry and the naming — and
    it removes them by construction rather than by a check afterwards.

    Two entries are forced rather than read from the settings, because neither
    has a defensible other value here: `colmapExportMasks` is what this export
    exists for, and `colmapMaskExtension` must be `CME_EXT` or the files land
    as `00000.mask.png`, which is RealityScan's own mask-layer convention and
    not a name LichtFeld Studio pairs with anything.

    The route it replaces was `-exportMapsAndMask folderName params.xml` and
    its `ei*` keys, recovered from the executable's string table and correct as
    far as they go — RealityScan honoured `eiExportImageList` and wrote
    `imageList.txt`. It then answered **"Feature not implemented"** and failed
    the export, on RealityScan 2.2.0.119430, with a real preview mesh and every
    image selected. So that verb is not a route on this build.
    """
    return build_colmap_export_params(
        colmap.model_copy(update={"export_masks": True, "mask_extension": "ext"}),
        dest,
    )


def check_format_registered(rc_exe: Path) -> dict:
    """Is the COLMAP exporter registered in *this* RealityScan install?

    The GUID above is the only thing that says which exporter `-exportRegistration`
    runs, and RealityScan resolves it against `calibration.xml` next to its own
    executable. When it does not resolve, RS does not fail and does not say so:
    measured on the staging workstation, all five projects exported to
    `<slug>_COLMAP/colmap.txt` a plain list of the *source* frame paths — which
    is byte for byte the body of the **first** `<format>` in the file,

        <format … desc="Image List" writer="cvs">
          <body>$ExportCameras($(imagePath)$(imageName)$(imageExt)
    )</body>

    — so an unresolved id falls back to format one. The alignment succeeds, the
    step reports success, and the defect only surfaces two steps later as
    "no cameras/images pair under sparse/0", or at the mask run, which cannot
    start without the dataset (step_masks.py). Same install, same params file,
    same RealityScan build (2.2.0.119430): the difference is the registration.

    Never raises — a check that cannot read the file answers `checked: False`
    and the run goes ahead, because an unreadable `calibration.xml` is not a
    reason to refuse an alignment.
    """
    report: dict = {
        "checked": False,
        "path": str(rc_exe.parent / "calibration.xml"),
        "registered": False,
        "writer": None,
        "fallback": None,
        "reason": None,
    }
    calibration = rc_exe.parent / "calibration.xml"
    if not calibration.is_file():
        report["reason"] = "no calibration.xml beside RealityScan.exe"
        return report

    try:
        formats = list(ET.parse(calibration).iter("format"))
    except (ET.ParseError, OSError) as exc:
        report["reason"] = f"calibration.xml could not be read ({exc})"
        return report

    report["checked"] = True
    if formats:
        report["fallback"] = formats[0].get("desc") or formats[0].get("id")

    wanted = COLMAP_FORMAT_ID.strip("{}").lower()
    for node in formats:
        if (node.get("id") or "").strip("{}").lower() == wanted:
            report["registered"] = True
            report["writer"] = node.get("writer")
            break
    else:
        report["reason"] = (
            f"format {COLMAP_FORMAT_ID} (COLMAP) is not among the "
            f"{len(formats)} export formats this install registers"
        )
    return report


def verify_against_saved_params(saved: Path) -> dict:
    """Compare our parameter names against an XML saved from RS's export dialog.

    The dialog can write its own settings out, and that file is the only
    authority on the enum tokens: RealityScan's string table contains
    `CDS_STANDARD`, `CFT_TXT` and `CME_EXT` but not their counterparts, so
    `CDS_FLAT`, `CFT_BIN` and `CME_MASK_EXT` above are inferred, and the two
    undistortion modes are emitted as combo indices. Loading the file does not
    validate any of them (a bad value is ignored, not refused), so a wrong one
    is only visible in the output. Point this at a saved file to find out which
    of them are wrong before a real run does it the expensive way.

    Returns {"unknown": [...], "missing": [...], "values": {...}} — parameters
    the saved file has and we do not, ones we emit and it does not, and the
    values it uses.
    """
    tree = ET.parse(saved)
    found: dict[str, str] = {}
    for node in tree.iter():
        # `key` is the settings-file spelling, `variable` the one a format
        # definition uses for the same parameter; accept either.
        name = node.get("key") or node.get("variable") or node.get("name")
        if name:
            found[name] = node.get("value") or (node.text or "").strip()

    ours = set(_colmap_params(ColmapExportDefaults()))
    return {
        "unknown": sorted(set(found) - ours),
        "missing": sorted(ours - set(found)),
        "values": found,
    }
