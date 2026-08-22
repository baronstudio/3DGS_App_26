import asyncio
import csv
import json
from pathlib import Path
from typing import Optional

from backend.core.config import app_config
from backend.core.defaults import RCDefaults, _deep_merge, load_defaults
from backend.core.proc import ProcessAborted, kill_tree, release, spawn
from backend.core.steps.rc_export_params import build_colmap_export_params
from backend.core.steps.rc_postprocess import (
    align_pointcloud_to_cameras,
    normalise_transforms,
)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


# -- Settings resolution -----------------------------------------------------

def resolve_rc_settings(settings: dict) -> RCDefaults:
    """Overlay the per-project settings onto the app defaults (CLAUDE.md 4).

    A project may send the rc block nested or flat; both are accepted, and only
    keys the model knows are taken - a stray UI field must not reach the .rscmd.

    The merge is deep because the colmap block is nested and a project stores
    only the keys it actually overrides. A flat `{**base, **patch}` would
    replace that whole sub-dict, resetting its siblings to the *model* defaults
    rather than the ones in defaults.json - the failure CLAUDE.md 4 forbids by
    name ("never a full copy of the defaults, or changing a default would stop
    propagating to existing projects").
    """
    base = load_defaults().rc.model_dump()
    incoming = settings or {}
    nested = incoming.get("rc")
    patch_source = nested if isinstance(nested, dict) else incoming
    patch = {k: v for k, v in patch_source.items() if k in base and v is not None}
    return RCDefaults.model_validate(_deep_merge(base, patch))


# -- Generated .rscmd --------------------------------------------------------

def build_rscmd(frames_dir: Path, rc_output: Path, rc: RCDefaults) -> Path:
    """Write the script RealityScan executes and return its path.

    Generated per run instead of shipped as a static file: `-mergeComponents` is
    absent from some RealityScan builds and an unknown verb makes RC exit
    non-zero, so the merge has to be switchable without hand-editing a file.

    Note what this does *not* do: it never splits the sequences. Image groups in
    RC are calibration groups inside one project - they do not partition the
    reconstruction. Every sequence goes through the same `-align`, and what we
    want out of it is a single component (CLAUDE.md 7).
    """
    lines = [f'-addFolder "{frames_dir}"']
    lines += [line.strip() for line in rc.extra_align_commands if line.strip()]
    lines.append("-align")
    if rc.merge_components:
        lines.append("-mergeComponents")
    if rc.keep_largest:
        lines.append("-selectMaximalComponent")
    lines += [
        f'-exportRegistration "{rc_output / "transforms.json"}"',
        f'-exportSparsePointCloud "{rc_output / "pointcloud.ply"}"',
    ]

    # The COLMAP dataset, written next to the NeRF one rather than instead of
    # it: the coverage check, the camera overlay and the preview all read
    # transforms.json, and LichtFeld Studio prefers COLMAP over it unprompted
    # ("COLMAP dataset detected" is probed before "Blender/NeRF dataset
    # detected"). With directory_structure "standard" RC writes images/ and
    # sparse/0/ itself, which is the layout that loader looks for first.
    if rc.colmap.enabled:
        params = build_colmap_export_params(
            rc.colmap, rc_output / "colmap_export_params.xml"
        )
        lines.append(
            f'-exportRegistration "{rc_output / "colmap.txt"}" "{params}"'
        )

    lines.append("-quit")
    script = rc_output / "align.rscmd"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return script


# -- Alignment coverage check ------------------------------------------------

def _input_frame_names(frames_dir: Path) -> list[str]:
    if not frames_dir.is_dir():
        return []
    return sorted(
        f.name for f in frames_dir.iterdir()
        if f.suffix.lower() in _IMAGE_SUFFIXES
    )


def _basename(raw: str) -> str:
    """Last path component of a path written by RC, on any host.

    RC writes Windows paths with backslashes and `Path()` only splits those when
    the interpreter itself runs on Windows - split on both separators so the
    check does not silently depend on where it executes.
    """
    return raw.replace("\\", "/").rsplit("/", 1)[-1]


def _dedup(names) -> list[str]:
    """Non-empty names, first occurrence wins, order preserved."""
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _registered_frame_names(rc_output: Path) -> tuple[list[str], Optional[str]]:
    """Camera names in whatever registration RC managed to export, in export order.

    transforms.json first, registration.csv as a fallback: which of the two
    exists depends on the export params, and the check must not depend on that.
    Order is preserved because the names are not always comparable to the input
    ones (see `_missing_frames`) - position is then the only link left.
    Returns (names, source_filename) - an empty list means we could not tell.
    """
    transforms = rc_output / "transforms.json"
    if transforms.exists():
        try:
            data = json.loads(transforms.read_text(encoding="utf-8"))
            names = _dedup(
                _basename(f.get("file_path", "")) for f in data.get("frames", [])
            )
            if names:
                return names, "transforms.json"
        except (json.JSONDecodeError, OSError):
            pass

    csv_path = rc_output / "registration.csv"
    if csv_path.exists():
        try:
            with open(csv_path, newline="", encoding="utf-8") as fh:
                names = _dedup(
                    _basename(row["#name"])
                    for row in csv.DictReader(fh)
                    if row.get("#name")
                )
            if names:
                return names, "registration.csv"
        except (OSError, KeyError):
            pass

    return [], None


def _missing_frames(
    input_names: list[str], registered: list[str]
) -> tuple[set[str], int, str]:
    """Which of the input frames did not come back registered.

    Names are the natural key, but `-exportRegistration` to a NeRF
    transforms.json does not keep them: RC exports undistorted copies renamed
    `00000.png`, `00001.png`... so a fully aligned project matches zero names
    and used to be reported as 0/N aligned. When *nothing* matches by name, fall
    back to position - RC exports in the order the images were added, which is
    the sorted input order.

    Returns (missing_names, missing_count, matched_by) where `matched_by` is the
    key that worked: "name", "position", or "count" when the export was renamed
    *and* short, leaving only the totals comparable.
    """
    if not registered:
        return set(input_names), len(input_names), "name"

    known = set(registered)
    if any(n in known for n in input_names):
        missing = {n for n in input_names if n not in known}
        return missing, len(missing), "name"

    # No name in common at all: renamed export, not 100% missing frames.
    if len(registered) == len(input_names):
        return set(), 0, "position"

    # Renamed *and* short - we know how many cameras are absent, not which.
    return set(), max(len(input_names) - len(registered), 0), "count"


def _sequence_index(project_path: Path) -> dict[str, int]:
    """filename -> sequence_id, from the curation scores. {} before analysis."""
    scores_path = project_path / "analysis" / "scores.json"
    if not scores_path.exists():
        return {}
    try:
        data = json.loads(scores_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        f["filename"]: int(f.get("sequence_id", 0))
        for f in data.get("frames", [])
        if f.get("filename")
    }


def _sequence_breakdown(
    input_names: list[str], missing: set[str], by_sequence: dict[str, int]
) -> list[dict]:
    """Per-sequence input / aligned / missing counts, sorted by sequence id."""
    if not by_sequence:
        return []
    stats: dict[int, dict] = {}
    for name in input_names:
        sid = by_sequence.get(name)
        if sid is None:
            continue
        row = stats.setdefault(sid, {"sequence_id": sid, "input": 0, "missing": 0})
        row["input"] += 1
        if name in missing:
            row["missing"] += 1
    for row in stats.values():
        row["aligned"] = row["input"] - row["missing"]
    return [stats[k] for k in sorted(stats)]


async def check_alignment_coverage(
    project_path: Path, rc_output: Path, broadcast_fn
) -> dict:
    """Compare what we fed RC against what came back registered.

    `-selectMaximalComponent` keeps the largest component and drops the rest
    without a word; a 60/40 split then trains LichtFeld on 60% of the scene and
    simply looks "incomplete" for no visible reason. This is the only place that
    difference becomes visible. It warns and never fails - a couple of genuinely
    unalignable frames must not block the pipeline, and the decision to re-align
    belongs to the user.

    Writes rc_output/alignment_check.json and returns the same payload. Never
    raises: a broken report must not sink a good alignment.
    """
    try:
        input_names = _input_frame_names(project_path / "frames")
        registered, source = _registered_frame_names(rc_output)

        if not input_names or source is None:
            await broadcast_fn(
                "rc", "WARNING",
                "[RS] Alignment coverage unknown - no registration export found "
                "to compare against the input frames.",
            )
            report = {
                "checked": False,
                "reason": "no registration export" if input_names else "no input frames",
                "input_count": len(input_names),
                "aligned_count": 0,
                "missing_count": 0,
                "aligned_ratio": None,
                "single_component": None,
                "missing_frames": [],
                "sequences": [],
                "source": source,
                "matched_by": None,
            }
        else:
            missing, missing_count, matched_by = _missing_frames(
                input_names, registered
            )
            aligned = len(input_names) - missing_count
            ratio = aligned / len(input_names)
            sequences = _sequence_breakdown(
                input_names, missing, _sequence_index(project_path)
            )
            report = {
                "checked": True,
                "reason": None,
                "input_count": len(input_names),
                "aligned_count": aligned,
                "missing_count": missing_count,
                "aligned_ratio": round(ratio, 4),
                "single_component": missing_count == 0,
                "missing_frames": sorted(missing),
                "sequences": sequences,
                "source": source,
                "matched_by": matched_by,
            }

            if missing_count == 0:
                renamed = (
                    " RS renamed the exported images, so the cameras were "
                    "matched by export order."
                ) if matched_by == "position" else ""
                await broadcast_fn(
                    "rc", "SUCCESS",
                    f"[RS] Coverage OK - {aligned}/{len(input_names)} cameras "
                    f"registered, single component.{renamed}",
                )
            else:
                hit = [s for s in sequences if s["missing"]]
                seq_txt = (
                    " Affected sequences: " + ", ".join(
                        f"#{s['sequence_id']} ({s['missing']}/{s['input']} missing)"
                        for s in hit
                    ) + "."
                ) if hit else ""
                if missing:
                    sample = ", ".join(sorted(missing)[:8])
                    more = f" (+{len(missing) - 8} more)" if len(missing) > 8 else ""
                    which = f" Missing: {sample}{more}."
                else:
                    which = (
                        " RS renamed the exported images, so which frames were "
                        "dropped cannot be read from the export - only how many."
                    )
                await broadcast_fn(
                    "rc", "WARNING",
                    f"[RS] Alignment split - {aligned}/{len(input_names)} cameras "
                    f"registered ({ratio:.1%}). {missing_count} frames landed in "
                    f"another component and were dropped.{seq_txt}{which} Fix: "
                    f"re-align with a higher image overlap, keep the frames the "
                    f"overlap gate rejected around the cuts, or merge the "
                    f"components with control points in the RealityScan GUI.",
                )

        rc_output.mkdir(parents=True, exist_ok=True)
        (rc_output / "alignment_check.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        return report

    except Exception as exc:  # never sink a good alignment over the report
        await broadcast_fn(
            "rc", "WARNING", f"[RS] Alignment coverage check skipped: {exc}"
        )
        return {"checked": False, "reason": str(exc)}


# ── RC runner ───────────────────────────────────────────────────────────────

async def run_rc(project_path: Path, broadcast_fn, settings: dict) -> dict:
    """Calls RealityScan.exe headless with the .rscmd generated for this run."""
    rc_exe_str = app_config.tools.rc_exe_path
    if not rc_exe_str:
        raise FileNotFoundError(
            "rc_exe_path is not configured.\n"
            "Install RealityScan via the Epic Games Launcher and set rc_exe_path in Settings."
        )
    rc_exe = Path(rc_exe_str)
    if not rc_exe.exists():
        raise FileNotFoundError(
            f"RealityScan.exe not found at: {rc_exe}\n"
            "Install RealityScan via the Epic Games Launcher and set rc_exe_path in Settings."
        )

    frames_dir = project_path / "frames"
    rc_output = project_path / "rc_output"
    rc_output.mkdir(exist_ok=True)

    rc = resolve_rc_settings(settings)
    script = build_rscmd(frames_dir, rc_output, rc)
    await broadcast_fn(
        "rc", "INFO",
        "[RS] Script:\n  " + script.read_text(encoding="utf-8").strip().replace("\n", "\n  "),
    )

    cmd = [str(rc_exe), "-headless", "-execRSCMD", str(script)]
    await broadcast_fn("rc", "INFO", f"[RS] Launching: {' '.join(cmd)}")

    loop = asyncio.get_running_loop()

    # Registered so /control abort can kill the tree from the outside — RC
    # launches workers of its own, so only a tree kill frees the GPU (core/proc.py).
    proc = spawn(cmd, project_path)

    try:
        while True:
            raw = await loop.run_in_executor(None, proc.stdout.readline)
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            await broadcast_fn("rc", _classify_rc_line(line), line)

        returncode = await loop.run_in_executor(None, proc.wait)
    except asyncio.CancelledError:
        kill_tree(proc)
        raise
    finally:
        killed = release(project_path, proc)

    if killed:
        raise ProcessAborted("RealityScan was stopped by the user.")

    if returncode != 0:
        raise RuntimeError(f"RealityScan exited with code {returncode}")

    if rc.normalise_for_lfs:
        await _normalise_export_for_lfs(rc_output, broadcast_fn)

    await broadcast_fn("rc", "INFO", "[RS] Alignment complete - checking coverage.")
    coverage = await check_alignment_coverage(project_path, rc_output, broadcast_fn)

    aligned = coverage.get("aligned_count")
    tail = f" ({aligned}/{coverage.get('input_count')} cameras)" if aligned else ""
    await broadcast_fn("rc", "SUCCESS", f"[RS] Step complete{tail}.", progress=1.0)
    return {"rc_output": str(rc_output), "alignment": coverage}


async def _normalise_export_for_lfs(rc_output: Path, broadcast_fn) -> dict:
    """Reconcile RC's two exporters with each other and with the LFS loader.

    Never raises - a failed rewrite is worth a warning, not a dead alignment.
    See rc_postprocess.py for what the two fixes are and why.
    """
    report: dict = {}
    try:
        report["transforms"] = normalise_transforms(rc_output)
        if report["transforms"].get("patched"):
            await broadcast_fn(
                "rc", "INFO",
                f"[RS] transforms.json normalised for LichtFeld Studio - "
                f"{report['transforms']['camera_model']} intrinsics hoisted to the "
                f"top level over {report['transforms']['frames']} frames.",
            )
        report["pointcloud"] = align_pointcloud_to_cameras(rc_output)
        if report["pointcloud"].get("rotated"):
            await broadcast_fn(
                "rc", "INFO",
                f"[RS] Sparse cloud rotated into the camera frame "
                f"({report['pointcloud']['rotation']}, "
                f"{report['pointcloud']['points']:,} points) - RS exports the "
                f"cloud Z-up and the registration Y-up.",
            )
        elif report["pointcloud"].get("reason") not in (None, "already rotated"):
            await broadcast_fn(
                "rc", "WARNING",
                f"[RS] Sparse cloud left in RS's frame: "
                f"{report['pointcloud']['reason']}. It will not line up with the "
                f"cameras in LichtFeld Studio.",
            )
    except Exception as exc:
        await broadcast_fn(
            "rc", "WARNING",
            f"[RS] Could not normalise the export for LichtFeld Studio: {exc}",
        )
        report["error"] = str(exc)
    return report


def _classify_rc_line(line: str) -> str:
    ll = line.lower()
    if "error" in ll or "failed" in ll:
        return "ERROR"
    if "warning" in ll:
        return "WARNING"
    if "aligned" in ll or "export" in ll or "done" in ll:
        return "SUCCESS"
    return "INFO"
