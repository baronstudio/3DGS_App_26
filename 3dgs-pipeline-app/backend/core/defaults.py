"""
defaults.py — business defaults per wizard step, persisted in defaults.json.

Layer 2 of the three-layer settings model (CLAUDE.md §4):

    config.json           → installation: exe paths, URLs         (core/config.py)
    defaults.json         → business defaults per step            ← this module
    Project.settings_json → per-project overrides, always win

Pure module: no FastAPI import here, so the pipeline and the tests can read the
defaults without spinning up the API.
"""

import json
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

DEFAULTS_PATH = Path(__file__).parent.parent.parent / "defaults.json"

SCHEMA_VERSION = 1


# ── Capture presets ──────────────────────────────────────────────────────────
# Code-defined and read-only: a preset added in a later version must reach
# existing installs, which it would not if presets lived in defaults.json.
# target_frame_count and the overlap band travel together because they are two
# views of the same physical quantity — how fast the camera moves through space.

class CapturePreset(BaseModel):
    id: str
    label: str
    target_frame_count: int
    min_fps: float
    max_fps: float
    overlap_min_step_pct: float
    overlap_band_max_pct: float
    notes: str = ""


CAPTURE_PRESETS: list[CapturePreset] = [
    CapturePreset(
        id="orbit_drone",
        label="Drone orbit",
        target_frame_count=300,
        min_fps=0.5,
        max_fps=6.0,
        overlap_min_step_pct=2.0,
        overlap_band_max_pct=12.0,
        notes="Smooth continuous orbit around a subject. Constant motion, few cuts.",
    ),
    CapturePreset(
        id="handheld_walk",
        label="Handheld walkthrough",
        target_frame_count=450,
        min_fps=1.0,
        max_fps=10.0,
        overlap_min_step_pct=2.0,
        overlap_band_max_pct=10.0,
        notes="Irregular speed and more motion blur — extract denser, let the blur "
              "filter cut. Tighter overlap band because the path is not smooth.",
    ),
    CapturePreset(
        id="turntable",
        label="Turntable / object",
        target_frame_count=200,
        min_fps=0.5,
        max_fps=5.0,
        overlap_min_step_pct=1.5,
        overlap_band_max_pct=8.0,
        notes="Object rotates, camera fixed. Regular angular step, so a narrow band "
              "is safe and redundant frames are cheap to drop.",
    ),
    CapturePreset(
        id="interior_scan",
        label="Interior scan",
        target_frame_count=600,
        min_fps=1.0,
        max_fps=12.0,
        overlap_min_step_pct=2.5,
        overlap_band_max_pct=9.0,
        notes="Confined space: parallax grows fast, so keep more frames and a "
              "conservative max step to avoid alignment breaks.",
    ),
]

PRESETS_BY_ID: dict[str, CapturePreset] = {p.id: p for p in CAPTURE_PRESETS}


# ── Per-step defaults ────────────────────────────────────────────────────────

FpsMode = Literal["auto", "ratio", "absolute"]


class ExtractDefaults(BaseModel):
    capture_preset: str = "orbit_drone"
    fps_mode: FpsMode = "auto"
    # Fraction of the source cadence. 0.2 is JB's habitual value and the
    # RealityScan video-import default: on a 100 fps rush it yields 20 img/s.
    fps_ratio: float = 0.2
    fps_absolute: float = 2.0
    target_frame_count: int = 300
    # OFF on purpose: mpdecimate duplicates the overlap gate AND drops frames
    # non-deterministically, which breaks the frame-index ↔ timecode mapping that
    # scene detection and the timeline rely on. See CLAUDE.md §6.1.
    mpdecimate: bool = False
    quality: int = 2
    max_frames: int = 0


class CurateDefaults(BaseModel):
    enabled: bool = True
    auto_after_extract: bool = True
    scene_detector: Literal["adaptive", "content", "off"] = "adaptive"
    min_scene_len: int = 15
    sharpness_window: int = 15
    # 0-100. The fraction of the local sharpness median a frame must reach:
    # 0 rejects nothing, 50 rejects anything under half the median.
    sharpness_sensitivity: int = 50
    # When true the band below is taken from the active capture preset, which is
    # where it belongs (§6.2: the preset describes how fast the camera travels).
    # Turn it off to pin the band by hand for one project.
    overlap_from_preset: bool = True
    overlap_min_step_pct: float = 2.0
    overlap_band_max_pct: float = 12.0


class UndistortDefaults(BaseModel):
    """RealityScan's "Undistortion settings" block, as the export dialog shows it.

    Not a free choice: RC refuses to write a COLMAP camera for its own
    `division` distortion model ("COLMAP does not support the distortion model
    'division' used during alignment. Export with respect to undistorted images
    instead."), and the model id it falls back to is 13, which is not a COLMAP
    model at all — LichtFeld Studio answers that with `Invalid camera model ID
    13 for image`. So `enabled` and `export_images` stay on unless the whole
    COLMAP export is off.
    """
    enabled: bool = True
    # Which part of the undistorted frame survives the crop. RC crops every
    # image slightly differently, which is exactly why COLMAP (one intrinsic
    # per image) beats the NeRF path (one intrinsic for all of them).
    fit: Literal["outer_boundary", "inner_region", "in_between"] = "inner_region"
    resolution: Literal["preserve", "custom", "fit"] = "fit"
    custom_width: int = 0
    custom_height: int = 0
    downscale: int = 1
    undistort_principal_point: bool = True
    image_cutout: float = 1.0
    # 0 = no resampling. Anything else silently rescales the intrinsics too.
    max_pixels: int = 0
    export_images: bool = True
    image_format: Literal["png", "jpg", "tiff"] = "png"
    pixel_format: str = "24-bit BGR"
    naming_convention: Literal["sequential", "original"] = "sequential"
    background_color: str = "#000000"


class ColmapExportDefaults(BaseModel):
    """The COLMAP registration export of step 3 (TODO P1).

    RealityScan 2.2 ships the exporter — `calibration.xml` registers format
    `{280B11A4-F9A3-47D1-AE58-C0DEA33487D8}` with
    `writer="RealityScan.Export.COLMAP"` — so this block is the dialog's
    parameters, not an invention of ours.
    """
    enabled: bool = True
    # "COLMAP standard" is RC's own wording for images/ + sparse/0/, which is
    # the layout LichtFeld Studio's loader looks for first. "flat" drops
    # everything in one directory; LFS copes ("Detected flat structure - using
    # root directory for images") but nothing else does.
    directory_structure: Literal["standard", "flat"] = "standard"
    # LFS prefers binary when both are present ("Found both binary and text
    # COLMAP files. Prioritizing binary files."), and points3D in ASCII is a
    # couple of hundred megabytes for a real alignment.
    file_type: Literal["binary", "ascii"] = "binary"
    # Tie points RC flagged weak, ill-conditioned or outlier. They seed the
    # gaussians, so a cleaner cloud is worth more here than a bigger one.
    exclude_unreliable_tie_points: bool = True
    # Off by default: this app has no mask source (the SAM 2 module of §9 is
    # deferred), so there is nothing to export.
    export_masks: bool = False
    mask_extension: Literal["ext", "mask_ext"] = "mask_ext"
    # "Export transformation settings" -> "Rotate X" in the dialog, and the
    # reason the trained splat comes out the right way up.
    #
    # RC's COLMAP template already rotates the scene by Rx+90,
    # `(x, y, z) -> (x, -z, y)`, which sends RC's +Z onto -Y. LFS's NeRF loader
    # cancels that with its own Rx+180; its COLMAP loader does not, because
    # COLMAP is already the convention it wants. 180 here composes to Rx-90
    # overall, `(x, y, z) -> (x, z, -y)`, so a COLMAP-trained splat lands in
    # exactly the frame a transforms.json-trained one does today and nothing
    # downstream — viewer/frame.ts, export/, Blender — has to change.
    #
    # The order RC applies it in does not matter: rotations about the same axis
    # commute, so 180 before or after the template's swap gives the same frame.
    # Set 0 for a scene where RC's +Z was never the true vertical.
    scene_rotate_x_deg: float = 180.0
    undistort: UndistortDefaults = Field(default_factory=UndistortDefaults)


class RCDefaults(BaseModel):
    precision: Literal["Preview", "Normal", "High"] = "Normal"
    max_features: int = 60000
    # Keep only the largest component. An alignment that splits produces several
    # components, each in its own arbitrary coordinate frame — LFS can consume
    # exactly one, so this stays on. What it discards is reported, never silent.
    keep_largest: bool = True
    # -mergeComponents before the maximal-component selection. The verb is not
    # present in every RealityScan build; turn it off if the CLI rejects it.
    merge_components: bool = True
    # Rewrite RC's export into what the LichtFeld Studio loader reads: top-level
    # PINHOLE intrinsics in transforms.json, and the sparse cloud rotated from
    # RC's Z-up frame into the NeRF Y-up one the registration uses. Off only if
    # a future RC build starts exporting both in agreement.
    normalise_for_lfs: bool = True
    # COLMAP registration export (TODO P1). Kept alongside transforms.json, not
    # instead of it: the coverage check, the camera overlay and the preview all
    # read the NeRF export, and LFS picks COLMAP over it on its own anyway.
    colmap: ColmapExportDefaults = Field(default_factory=ColmapExportDefaults)
    # Raw .rscmd lines injected before -align, used verbatim. Escape hatch for
    # verbs this app does not model (alignment -set parameters, marker import…)
    # without having to patch step_rc.py.
    extra_align_commands: list[str] = Field(default_factory=list)


class LFSDefaults(BaseModel):
    iterations: int = 30000
    # v0.5.3 strategies; "default" sends no flag and lets the build pick (MRNF).
    strategy: Literal["default", "mcmc", "mrnf", "igs+"] = "default"
    eval: bool = False
    save_eval_images: bool = False
    background_color: str = "#000000"


class ExportDefaults(BaseModel):
    format: Literal["ply", "splat"] = "ply"
    pattern: str = "{project}_{index:05d}"


class BlenderDefaults(BaseModel):
    scene_scale: float = 1.0
    import_mode: str = "splatforge"


class ViewerDefaults(BaseModel):
    """The 3D preview in steps 3, 4 and 5.

    `preview_max_points` is what the viewer opens at, not a ceiling: the "full
    quality" button asks for the whole file. It exists because the LFS splat is
    measured in gigabytes and the first thing you want is a picture, not a
    perfect picture. 0 opens at full quality.
    """
    preview_max_points: int = 1_000_000
    point_size: float = 1.6
    show_cameras: bool = True
    show_camera_path: bool = True
    background: str = "#0b1220"


class AppDefaults(BaseModel):
    schema_version: int = SCHEMA_VERSION
    extract: ExtractDefaults = Field(default_factory=ExtractDefaults)
    curate: CurateDefaults = Field(default_factory=CurateDefaults)
    rc: RCDefaults = Field(default_factory=RCDefaults)
    lfs: LFSDefaults = Field(default_factory=LFSDefaults)
    export: ExportDefaults = Field(default_factory=ExportDefaults)
    blender: BlenderDefaults = Field(default_factory=BlenderDefaults)
    viewer: ViewerDefaults = Field(default_factory=ViewerDefaults)


SECTIONS = ("extract", "curate", "rc", "lfs", "export", "blender", "viewer")


# ── Load / save ──────────────────────────────────────────────────────────────

def _deep_merge(base: dict, patch: dict) -> dict:
    """Merge patch into base recursively. Patch values win; base keys survive."""
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_defaults() -> AppDefaults:
    """Read defaults.json, creating it from the code defaults if absent.

    Unknown keys are ignored and missing keys fall back to the model defaults,
    so an older defaults.json keeps working after a new field is added.
    """
    if not DEFAULTS_PATH.exists():
        fresh = AppDefaults()
        _write(fresh)
        return fresh
    try:
        with open(DEFAULTS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        # A corrupt file must not brick the app — fall back to code defaults.
        return AppDefaults()
    return AppDefaults.model_validate(_deep_merge(AppDefaults().model_dump(), raw))


def _write(defaults: AppDefaults) -> None:
    with open(DEFAULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(defaults.model_dump(), f, indent=4)


def save_defaults(patch: dict[str, Any]) -> AppDefaults:
    """Deep-merge a partial payload over the stored defaults and persist."""
    current = load_defaults().model_dump()
    merged = AppDefaults.model_validate(_deep_merge(current, patch))
    merged.schema_version = SCHEMA_VERSION
    _write(merged)
    return reload_defaults()


def reset_defaults(section: Optional[str] = None) -> AppDefaults:
    """Factory-reset every section, or a single one when `section` is given."""
    if section is None:
        fresh = AppDefaults()
        _write(fresh)
        return reload_defaults()
    if section not in SECTIONS:
        raise ValueError(f"Unknown section '{section}'. Expected one of {SECTIONS}.")
    current = load_defaults().model_dump()
    current[section] = getattr(AppDefaults(), section).model_dump()
    _write(AppDefaults.model_validate(current))
    return reload_defaults()


def reload_defaults() -> AppDefaults:
    """Reload from disk and refresh the module-level singleton."""
    global app_defaults
    app_defaults = load_defaults()
    return app_defaults


# ── Working fps resolution ───────────────────────────────────────────────────

def resolve_extract_fps(
    extract: ExtractDefaults,
    source_fps: Optional[float] = None,
    duration_s: Optional[float] = None,
) -> tuple[float, str]:
    """Resolve the FFmpeg working fps from the policy and the probed source.

    Returns (fps, explanation). The explanation is logged and shown in the UI so
    the number is never a black box.
    """
    preset = PRESETS_BY_ID.get(extract.capture_preset)

    def by_ratio(reason: str = "") -> tuple[float, str]:
        if source_fps and source_fps > 0:
            fps = round(extract.fps_ratio * source_fps, 3)
            return fps, f"{reason}ratio {extract.fps_ratio} x {source_fps:g} fps source = {fps:g} fps"
        return (
            extract.fps_absolute,
            f"{reason}source cadence unknown - falling back to {extract.fps_absolute:g} fps",
        )

    if extract.fps_mode == "absolute":
        return extract.fps_absolute, f"fixed at {extract.fps_absolute:g} fps"

    if extract.fps_mode == "ratio":
        return by_ratio()

    # auto: aim for the preset's target frame count over the real duration.
    if not duration_s or duration_s <= 0:
        return by_ratio("duration unknown - ")

    target = extract.target_frame_count or (preset.target_frame_count if preset else 300)
    fps = target / duration_s

    lo = preset.min_fps if preset else 0.1
    hi = preset.max_fps if preset else 30.0
    clamped = min(max(fps, lo), hi)
    # Never ask FFmpeg for more frames than the source actually holds.
    if source_fps and source_fps > 0:
        clamped = min(clamped, source_fps)

    fps_r = round(clamped, 3)
    note = "" if abs(clamped - fps) < 1e-6 else f" (clamped from {fps:.3g})"
    label = preset.label if preset else "no preset"
    return fps_r, f"auto: {target} frames over {duration_s:.1f}s = {fps_r:g} fps{note} [{label}]"


app_defaults: AppDefaults = load_defaults()
