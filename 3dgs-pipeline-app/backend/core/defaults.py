"""
defaults.py — business defaults per wizard step, persisted in defaults.json.

Layer 2 of the three-layer settings model (CLAUDE.md §4):

    config.json           → installation: exe paths, stub flags   (core/config.py)
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
    # Raw .rscmd lines injected before -align, used verbatim. Escape hatch for
    # verbs this app does not model (alignment -set parameters, marker import…)
    # without having to patch step_rc.py.
    extra_align_commands: list[str] = Field(default_factory=list)


class LFSDefaults(BaseModel):
    iterations: int = 30000
    strategy: Literal["default", "mcmc"] = "default"
    lr: float = 0.001
    save_interval: int = 0
    render_mode: str = "RGB"
    eval: bool = False
    save_eval_images: bool = False
    background_color: str = "#000000"


class ExportDefaults(BaseModel):
    format: Literal["ply", "splat"] = "ply"
    pattern: str = "{project}_{index:05d}"


class BlenderDefaults(BaseModel):
    scene_scale: float = 1.0
    import_mode: str = "splatforge"


class AppDefaults(BaseModel):
    schema_version: int = SCHEMA_VERSION
    extract: ExtractDefaults = Field(default_factory=ExtractDefaults)
    curate: CurateDefaults = Field(default_factory=CurateDefaults)
    rc: RCDefaults = Field(default_factory=RCDefaults)
    lfs: LFSDefaults = Field(default_factory=LFSDefaults)
    export: ExportDefaults = Field(default_factory=ExportDefaults)
    blender: BlenderDefaults = Field(default_factory=BlenderDefaults)


SECTIONS = ("extract", "curate", "rc", "lfs", "export", "blender")


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
