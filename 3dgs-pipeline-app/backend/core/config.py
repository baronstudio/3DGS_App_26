import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.json"


class ToolPaths(BaseModel):
    rc_exe_path: Optional[str] = None
    lfs_exe_path: Optional[str] = None
    ffmpeg_path: str = ""
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
    """Reload config from disk and update the module-level singleton."""
    global app_config
    app_config = load_config()
    return app_config


app_config: AppConfig = load_config()
