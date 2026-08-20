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


class StubConfig(BaseModel):
    ffmpeg_stub: bool = False
    rc_stub: bool = True
    lfs_stub: bool = True
    blender_stub: bool = True
    rc_stub_duration_seconds: float = 8.0
    lfs_stub_duration_seconds: float = 15.0
    lfs_stub_iterations: int = 30000
    lfs_stub_fake_ply: bool = True


class AppConfig(BaseModel):
    tools: ToolPaths = ToolPaths()
    stubs: StubConfig = StubConfig()


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
        stubs=StubConfig(
            ffmpeg_stub=raw.get("ffmpeg_stub", False),
            rc_stub=raw.get("rc_stub", True),
            lfs_stub=raw.get("lfs_stub", True),
            blender_stub=raw.get("blender_stub", True),
            rc_stub_duration_seconds=raw.get("rc_stub_duration_seconds", 8.0),
            lfs_stub_duration_seconds=raw.get("lfs_stub_duration_seconds", 15.0),
            lfs_stub_iterations=raw.get("lfs_stub_iterations", 30000),
            lfs_stub_fake_ply=raw.get("lfs_stub_fake_ply", True),
        ),
    )


def save_config(cfg) -> None:
    """Save config to disk. Accepts AppConfig, a flat dict, or a nested one.

    config.json is flat on disk, but the API exposes the AppConfig shape
    (`{tools: {...}, stubs: {...}}`). A nested payload is flattened here rather
    than written verbatim, which would create dead `tools` / `stubs` keys that
    load_config never reads back.
    """
    if isinstance(cfg, dict):
        # Merge incoming dict over the existing file so no field is lost.
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                flat: dict = json.load(f)
        except Exception:
            flat = {}
        for key, value in cfg.items():
            if key in ("tools", "stubs") and isinstance(value, dict):
                flat.update(value)
            else:
                flat[key] = value
    else:
        flat = {}
        flat.update(cfg.tools.model_dump())
        flat.update(cfg.stubs.model_dump())
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(flat, f, indent=4)


def reload_config() -> AppConfig:
    """Reload config from disk and update the module-level singleton."""
    global app_config
    app_config = load_config()
    return app_config


app_config: AppConfig = load_config()
