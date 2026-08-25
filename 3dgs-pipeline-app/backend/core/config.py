import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.json"


# What `-hwaccel` is passed to FFmpeg. An installation setting, not a business
# one (CLAUDE.md §4): it describes the GPU in this machine, and no project wants
# a different one. "none" sends no flag at all.
#
# It is safe to be wrong about: FFmpeg treats `-hwaccel` as a preference, not a
# requirement — measured on a 4080x4080 h264 source, NVDEC refused the surface
# (`CUDA_ERROR_INVALID_VALUE`), FFmpeg fell back to software and the run still
# exited 0 with the right frames. step_extract watches for that line and says so,
# because a silent fallback is otherwise indistinguishable from a fast one.
HWACCELS = ("none", "auto", "cuda", "d3d11va", "dxva2", "qsv", "vulkan")


class ToolPaths(BaseModel):
    rc_exe_path: Optional[str] = None
    lfs_exe_path: Optional[str] = None
    ffmpeg_path: str = ""
    ffmpeg_hwaccel: str = "none"
    blender_exe_path: Optional[str] = None
    supersplat_url: str = ""


class AppConfig(BaseModel):
    tools: ToolPaths = ToolPaths()


def load_config() -> AppConfig:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return AppConfig(
        tools=ToolPaths(
            rc_exe_path=raw.get("rc_exe_path"),
            lfs_exe_path=raw.get("lfs_exe_path"),
            ffmpeg_path=raw.get("ffmpeg_path", ""),
            ffmpeg_hwaccel=raw.get("ffmpeg_hwaccel", "none") or "none",
            blender_exe_path=raw.get("blender_exe_path"),
            supersplat_url=raw.get("supersplat_url", ""),
        ),
    )


def save_config(cfg) -> None:
    """Save config to disk. Accepts AppConfig, a flat dict, or a nested one.

    config.json is flat on disk, but the API exposes the AppConfig shape
    (`{tools: {...}}`). A nested payload is flattened here rather than written
    verbatim, which would create a dead `tools` key that load_config never reads
    back.
    """
    if isinstance(cfg, dict):
        # Merge incoming dict over the existing file so no field is lost.
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                flat: dict = json.load(f)
        except Exception:
            flat = {}
        for key, value in cfg.items():
            if key == "tools" and isinstance(value, dict):
                flat.update(value)
            else:
                flat[key] = value
    else:
        flat = {}
        flat.update(cfg.tools.model_dump())
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(flat, f, indent=4)


def reload_config() -> AppConfig:
    """Reload config from disk into the existing singleton, in place.

    Mutated rather than rebound: every step does `from ...config import
    app_config`, which binds the object at import time. Rebinding the module
    global would leave all of them holding the *previous* config, so a tool path
    corrected in the Setup panel would not reach the steps until a restart —
    which is indistinguishable from the fix not working.
    """
    app_config.tools = load_config().tools
    return app_config


app_config: AppConfig = load_config()
