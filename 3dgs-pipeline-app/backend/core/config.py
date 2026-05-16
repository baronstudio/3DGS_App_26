import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.json"

_STUB_DEFAULTS = {
    "ffmpeg_stub": False,
    "rc_stub": False,
    "lfs_stub": False,
    "blender_stub": False,
    "rc_stub_duration_seconds": 30,
    "lfs_stub_duration_seconds": 120,
    "lfs_stub_iterations": 30,
    "lfs_stub_fake_ply": False,
}


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {
        "tools": {
            "rc_exe_path": raw.get("rc_exe_path"),
            "lfs_exe_path": raw.get("lfs_exe_path"),
            "ffmpeg_path": raw.get("ffmpeg_path", ""),
            "blender_exe_path": raw.get("blender_exe_path"),
            "supersplat_url": raw.get("supersplat_url", ""),
        },
        "stubs": {
            key: raw.get(key, default)
            for key, default in _STUB_DEFAULTS.items()
        },
    }


def save_config(config: dict) -> None:
    flat: dict = {}
    flat.update(config.get("tools", {}))
    flat.update(config.get("stubs", {}))
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(flat, f, indent=4)
