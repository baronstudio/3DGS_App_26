import asyncio
import csv
import json
import math
import random
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from backend.core.config import app_config
from backend.core.defaults import RCDefaults, load_defaults

_STUB_ASSETS = Path(__file__).parents[3] / "tools" / "test_assets"

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


# -- Settings resolution -----------------------------------------------------

def resolve_rc_settings(settings: dict) -> RCDefaults:
    """Overlay the per-project settings onto the app defaults (CLAUDE.md 4).

    A project may send the rc block nested or flat; both are accepted, and only
    keys the model knows are taken - a stray UI field must not reach the .rscmd.
    """
    base = load_defaults().rc.model_dump()
    incoming = settings or {}
    nested = incoming.get("rc")
    patch_source = nested if isinstance(nested, dict) else incoming
    patch = {k: v for k, v in patch_source.items() if k in base and v is not None}
    return RCDefaults.model_validate({**base, **patch})


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
        "-quit",
    ]
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
                "[RC] Alignment coverage unknown - no registration export found "
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
                    " RC renamed the exported images, so the cameras were "
                    "matched by export order."
                ) if matched_by == "position" else ""
                await broadcast_fn(
                    "rc", "SUCCESS",
                    f"[RC] Coverage OK - {aligned}/{len(input_names)} cameras "
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
                        " RC renamed the exported images, so which frames were "
                        "dropped cannot be read from the export - only how many."
                    )
                await broadcast_fn(
                    "rc", "WARNING",
                    f"[RC] Alignment split - {aligned}/{len(input_names)} cameras "
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
            "rc", "WARNING", f"[RC] Alignment coverage check skipped: {exc}"
        )
        return {"checked": False, "reason": str(exc)}



# ── Helpers ─────────────────────────────────────────────────────────────────

def _build_stub_transforms_json(project_path: Path, rc_output: Path) -> None:
    """Generate a transforms.json (NeRF format) compatible with LichtFeld Studio.

    Reads stub_registration.csv for known cameras and produces orbital poses
    for any additional frames found in project/frames/.
    Copies all frame images to rc_output/images/.
    """
    frames_dir = project_path / "frames"
    images_dir = rc_output / "images"
    images_dir.mkdir(exist_ok=True)

    frame_files = sorted(
        (f for f in frames_dir.iterdir()
         if f.suffix.lower() in (".jpg", ".jpeg", ".png")),
        key=lambda f: f.name,
    )

    default_fl = 2800.0
    default_w, default_h = 1920, 1080
    default_cx, default_cy = default_w / 2.0, default_h / 2.0

    # Load stub camera data (up to 3 keyframe entries)
    stub_cameras = {}
    stub_csv_path = _STUB_ASSETS / "stub_registration.csv"
    if stub_csv_path.exists():
        with open(stub_csv_path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                stub_cameras[row["#name"]] = row

    def _euler_to_c2w(heading_deg, pitch_deg, roll_deg, tx, ty, tz):
        """ZYX Euler (degrees) + translation → 4×4 camera-to-world matrix."""
        h = math.radians(heading_deg)
        p = math.radians(pitch_deg)
        r = math.radians(roll_deg)
        sh, ch = math.sin(h), math.cos(h)
        sp, cp = math.sin(p), math.cos(p)
        sr, cr = math.sin(r), math.cos(r)
        return [
            [ch * cp, ch * sp * sr - sh * cr, ch * sp * cr + sh * sr, tx],
            [sh * cp, sh * sp * sr + ch * cr, sh * sp * cr - ch * sr, ty],
            [-sp,     cp * sr,                cp * cr,                 tz],
            [0.0,     0.0,                    0.0,                    1.0],
        ]

    total = max(len(frame_files), 1)
    frames_data = []

    for i, frame_file in enumerate(frame_files):
        dst = images_dir / frame_file.name
        if not dst.exists():
            shutil.copy2(frame_file, dst)

        if frame_file.name in stub_cameras:
            row = stub_cameras[frame_file.name]
            fl = float(row["f"])
            px, py = float(row["ppx"]), float(row["ppy"])
            c2w = _euler_to_c2w(
                float(row["heading"]), float(row["pitch"]), float(row["roll"]),
                float(row["x"]), float(row["y"]), float(row["z"]),
            )
        else:
            # Orbital fallback for frames not in stub CSV
            angle = 2.0 * math.pi * i / total
            radius = 3.0
            x = radius * math.cos(angle)
            z = radius * math.sin(angle)
            heading_deg = math.degrees(math.atan2(-math.sin(angle), -math.cos(angle)))
            c2w = _euler_to_c2w(heading_deg, 0.0, 0.0, x, 0.5, z)
            fl, px, py = default_fl, default_cx, default_cy

        frames_data.append({
            "file_path": f"images/{frame_file.name}",
            "fl_x": fl,
            "fl_y": fl,
            "cx": px,
            "cy": py,
            "w": default_w,
            "h": default_h,
            "transform_matrix": c2w,
        })

    transforms = {
        "camera_model": "OPENCV",
        "fl_x": default_fl,
        "fl_y": default_fl,
        "cx": default_cx,
        "cy": default_cy,
        "w": default_w,
        "h": default_h,
        "aabb_scale": 16,
        "frames": frames_data,
    }

    out_path = rc_output / "transforms.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(transforms, fh, indent=2)


# ── Real RC runner ──────────────────────────────────────────────────────────

async def run_rc_real(project_path: Path, broadcast_fn, settings: dict) -> dict:
    """Calls RealityScan.exe headless with the .rscmd generated for this run."""
    rc_exe_str = app_config.tools.rc_exe_path
    if not rc_exe_str:
        raise FileNotFoundError(
            "rc_exe_path is not configured.\n"
            "Enable rc_stub in Settings, or install RealityCapture via Epic Games Launcher."
        )
    rc_exe = Path(rc_exe_str)
    if not rc_exe.exists():
        raise FileNotFoundError(
            f"RealityScan.exe not found at: {rc_exe}\n"
            "Enable rc_stub in Settings, or install RealityCapture via Epic Games Launcher."
        )

    frames_dir = project_path / "frames"
    rc_output = project_path / "rc_output"
    rc_output.mkdir(exist_ok=True)

    rc = resolve_rc_settings(settings)
    script = build_rscmd(frames_dir, rc_output, rc)
    await broadcast_fn(
        "rc", "INFO",
        "[RC] Script:\n  " + script.read_text(encoding="utf-8").strip().replace("\n", "\n  "),
    )

    cmd = [str(rc_exe), "-headless", "-execRSCMD", str(script)]
    await broadcast_fn("rc", "INFO", f"[RC] Launching: {' '.join(cmd)}")

    loop = asyncio.get_running_loop()

    # Use subprocess.Popen + run_in_executor to avoid NotImplementedError
    # on Windows when uvicorn runs with a SelectorEventLoop.
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    while True:
        raw = await loop.run_in_executor(None, proc.stdout.readline)
        if not raw:
            break
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        await broadcast_fn("rc", _classify_rc_line(line), line)

    returncode = await loop.run_in_executor(None, proc.wait)

    if returncode != 0:
        raise RuntimeError(f"RealityCapture exited with code {returncode}")

    await broadcast_fn("rc", "INFO", "[RC] Alignment complete - checking coverage.")
    coverage = await check_alignment_coverage(project_path, rc_output, broadcast_fn)

    aligned = coverage.get("aligned_count")
    tail = f" ({aligned}/{coverage.get('input_count')} cameras)" if aligned else ""
    await broadcast_fn("rc", "SUCCESS", f"[RC] Step complete{tail}.", progress=1.0)
    return {"rc_output": str(rc_output), "alignment": coverage}


def _classify_rc_line(line: str) -> str:
    ll = line.lower()
    if "error" in ll or "failed" in ll:
        return "ERROR"
    if "warning" in ll:
        return "WARNING"
    if "aligned" in ll or "export" in ll or "done" in ll:
        return "SUCCESS"
    return "INFO"


# ── Stub RC runner ──────────────────────────────────────────────────────────

async def run_rc_stub(project_path: Path, broadcast_fn, settings: dict) -> dict:
    """
    Simulates RealityCapture alignment with realistic progressive log output.
    Copies stub_registration.csv and sample.ply to rc_output/.
    Total duration: app_config.stubs.rc_stub_duration_seconds
    """
    rc_output = project_path / "rc_output"
    rc_output.mkdir(exist_ok=True)
    duration = app_config.stubs.rc_stub_duration_seconds
    frame_count = settings.get("frame_count", 120)
    rc = resolve_rc_settings(settings)

    await broadcast_fn(
        "rc", "INFO",
        "⚠️  [STUB MODE] RealityCapture is simulated — no real exe called.",
        progress=0.0,
    )
    await asyncio.sleep(0.5)

    # --- Phase 1: Loading images (0–15%)
    phase1_lines = [
        "RealityScan 1.5.1 (Build 12345) starting...",
        f"Loading {frame_count} images from input folder...",
        "Parsing EXIF metadata...",
        "Detected lens model: DJI Action Camera (fisheye, focal 4.38mm)",
        f"Grouping images by calibration: 1 group, {frame_count} images",
    ]
    for i, line in enumerate(phase1_lines):
        await broadcast_fn("rc", "INFO", line, progress=(i + 1) / len(phase1_lines) * 0.15)
        await asyncio.sleep(duration * 0.15 / len(phase1_lines))

    # --- Phase 2: Feature detection (15–40%)
    await broadcast_fn("rc", "INFO", "Detecting features (SIFT)...", progress=0.15)
    feature_steps = [
        (0.20, f"Processed {frame_count // 4} / {frame_count} images — features: 142,348"),
        (0.25, f"Processed {frame_count // 2} / {frame_count} images — features: 287,912"),
        (0.30, f"Processed {frame_count * 3 // 4} / {frame_count} images — features: 431,556"),
        (0.38, f"Processed {frame_count} / {frame_count} images — features: 578,204"),
        (0.40, "Feature detection complete. Total keypoints: 578,204"),
    ]
    for prog, line in feature_steps:
        await broadcast_fn("rc", "INFO", line, progress=prog)
        await asyncio.sleep(duration * 0.25 / len(feature_steps))

    # --- Phase 3: Matching (40–65%)
    await broadcast_fn("rc", "INFO", "Computing feature matches (exhaustive)...", progress=0.40)
    match_steps = [
        (0.48, f"Matching pair batch 1/4 — {random.randint(18000, 22000)} inliers"),
        (0.54, f"Matching pair batch 2/4 — {random.randint(16000, 21000)} inliers"),
        (0.59, f"Matching pair batch 3/4 — {random.randint(17000, 20000)} inliers"),
        (0.64, f"Matching pair batch 4/4 — {random.randint(15000, 19000)} inliers"),
        (0.65, "Matching complete. Connected components: 1"),
    ]
    for prog, line in match_steps:
        await broadcast_fn("rc", "INFO", line, progress=prog)
        await asyncio.sleep(duration * 0.25 / len(match_steps))

    # --- Phase 4: Bundle adjustment (65–88%)
    await broadcast_fn("rc", "INFO", "Running bundle adjustment (SfM)...", progress=0.65)
    ba_steps = [
        (0.70, f"Aligned {int(frame_count * 0.6)} / {frame_count} cameras..."),
        (0.75, f"Aligned {int(frame_count * 0.8)} / {frame_count} cameras..."),
        (0.80, f"Aligned {int(frame_count * 0.93)} / {frame_count} cameras..."),
        (0.84, f"Aligned {frame_count - random.randint(0, 3)} / {frame_count} cameras"),
        (0.87, f"Reprojection error: {random.uniform(0.4, 0.7):.3f} px (good)"),
        (0.88, "Bundle adjustment converged."),
    ]
    for prog, line in ba_steps:
        await broadcast_fn("rc", "INFO", line, progress=prog)
        await asyncio.sleep(duration * 0.23 / len(ba_steps))

    # --- Phase 5: Export (88–100%)
    if rc.merge_components:
        await broadcast_fn("rc", "INFO", "Merging components...", progress=0.89)
    if rc.keep_largest:
        await broadcast_fn("rc", "INFO", "Selecting maximal component...", progress=0.90)
    await asyncio.sleep(duration * 0.04)
    await broadcast_fn("rc", "INFO", "Exporting registration (transforms.json)...", progress=0.93)

    shutil.copy(
        _STUB_ASSETS / "stub_registration.csv",
        rc_output / "registration.csv",
    )
    _build_stub_transforms_json(project_path, rc_output)
    await asyncio.sleep(duration * 0.03)
    await broadcast_fn("rc", "INFO", "Exporting sparse point cloud (PLY)...", progress=0.97)
    shutil.copy(
        _STUB_ASSETS / "sample.ply",
        rc_output / "pointcloud.ply",
    )
    await asyncio.sleep(duration * 0.03)

    # The stub registers every frame, so the check passes - but it runs on the
    # same code path as a real run, which is the point of stub mode (CLAUDE.md 2).
    coverage = await check_alignment_coverage(project_path, rc_output, broadcast_fn)

    camera_count = coverage.get("aligned_count") or frame_count
    point_count = random.randint(180_000, 320_000)
    await broadcast_fn(
        "rc", "SUCCESS",
        f"[STUB] RealityCapture complete. "
        f"Cameras aligned: {camera_count}/{coverage.get('input_count', frame_count)} | "
        f"Sparse points: {point_count:,} | "
        f"Output: {rc_output}",
        progress=1.0,
    )
    return {
        "rc_output": str(rc_output),
        "camera_count": camera_count,
        "alignment": coverage,
    }


# ── Dispatcher ──────────────────────────────────────────────────────────────

async def run_rc(project_path: Path, broadcast_fn, settings: dict) -> dict:
    if app_config.stubs.rc_stub:
        return await run_rc_stub(project_path, broadcast_fn, settings)
    return await run_rc_real(project_path, broadcast_fn, settings)
