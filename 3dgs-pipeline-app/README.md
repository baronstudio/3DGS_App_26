# 3DGS Pipeline App — installation and use

This is the application itself. For what the project *is*, see the
[repository README](../README.md); for how it is built, see
[DEVELOPING.md](../DEVELOPING.md).

---

## 1. Prerequisites

The app orchestrates four external tools. It never bundles them: you install
them yourself and tell the app where they are.

| Requirement | Version | Notes |
|---|---|---|
| **NVIDIA GPU** | CUDA 12.8+ | required by the training step |
| **Python** | 3.11 or higher | backend |
| **Node.js** | 20 or higher | frontend |
| **FFmpeg** | any recent build | frame extraction; provides `ffmpeg` and `ffprobe` |
| **RealityScan** | 2.2 | alignment. Installed via the Epic Games Launcher. *Not* the older RealityCapture |
| **LichtFeld Studio** | v0.5.3 | training. Prebuilt Windows release, or built from source |
| **Blender** | 4.x / 5.x | only needed for step 6 |
| **Git** | any | to fetch dependencies |

Windows is the supported platform. The pipeline is Windows-first because three
of the four tools are.

> **Version pinning is not cosmetic.** RealityScan 2.2 and LichtFeld Studio
> v0.5.3 are the versions the app is written against, and both changed their
> command-line surface between releases. LichtFeld Studio v0.5.3 in particular
> renamed its training strategies and reports progress in a format earlier
> versions did not use. A different version may still run — it may also fail in
> ways the app cannot explain.

---

## 2. Installation

```bash
cd 3dgs-pipeline-app
python setup.py
```

`setup.py` creates the Python virtual environment, installs the backend
dependencies, installs the frontend packages and attempts to detect your tool
paths.

> ⚠ **Do not re-run `setup.py` on a working installation.** It rewrites
> `config.json` from scratch, and in a shape the application does not read back
> — every tool path you had configured is silently lost. Re-run it only on a
> fresh checkout, and edit `config.json` by hand or through the Settings panel
> afterwards. See [DEVELOPING.md](../DEVELOPING.md) for the detail.

If you prefer to do it by hand:

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt   # Windows
cd frontend && npm install
```

Install the backend dependencies from **`requirements.txt` at this directory's
root** — that is the current list. (`backend/requirements.txt` is an older,
incomplete copy: it is missing the curation dependencies entirely.)

### LichtFeld Studio

Either download the prebuilt v0.5.3 Windows release, or build it from source
following the [LichtFeld Studio Wiki](https://github.com/MrNeRF/LichtFeld-Studio/wiki).
Either way, point `lfs_exe_path` at the resulting `LichtFeld-Studio.exe`.

---

## 3. Configuring your tool paths

`config.json`, at this directory's root, holds one flat object — **where your
tools are installed**, and nothing else:

```json
{
    "rc_exe_path":      "C:\\Program Files\\Epic Games\\RealityScan_2.2\\RealityScan.exe",
    "lfs_exe_path":     "C:\\Program Files\\LichtFeld-Studio-windows-v0.5.3\\bin\\LichtFeld-Studio.exe",
    "ffmpeg_path":      "C:\\ffmpeg\\bin\\ffmpeg.exe",
    "blender_exe_path": "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe"
}
```

You can edit the file directly, or set the paths in the app: the **gear icon**
in the top bar opens the setup panel, under **Tools**.

The app will not let you start the pipeline until at least `rc_exe_path` and
`lfs_exe_path` are set. A missing or wrong path fails the step it belongs to,
and the error names the exact path it looked for — there is no simulation mode
and no silent fallback.

### The three settings layers

Tool paths are one of three distinct kinds of setting, and they are kept apart
on purpose:

| Layer | Where | What it holds | Where you edit it |
|---|---|---|---|
| **Installation** | `config.json` | executable paths | setup panel → Tools |
| **Defaults** | `defaults.json` | the default value of every step's settings — sampling policy, curation thresholds, alignment options, training iterations, viewer | setup panel → one section per step |
| **Per project** | the project's own record | only what you changed *for this project* | each step's **Advanced** panel |

**Per project beats defaults beats the built-in fallback.** A project stores
only the keys it actually overrides, so changing a default later still reaches
every existing project that never touched that key.

---

## 4. Running

```bat
start.bat
```

On Linux/macOS: `./start.sh`.

This starts two servers — the FastAPI backend on port **8000** and the Vite
frontend on port **5173**. Open **http://localhost:5173**; the frontend proxies
everything it needs to the backend, so port 8000 is not the address to use.

To stop, close both console windows.

---

## 5. Your first project

1. **Import.** Create a project and upload a video. This is the only step whose
   output a reset never deletes — you will not be asked to re-upload.

2. **Extract + curate.** Choose how densely to sample the video, then launch.
   Frames are extracted, then analysed automatically.

   The sampling rate has three modes. **Auto** (the default) works backwards
   from a target frame count and the video's real duration. **Ratio** takes a
   fraction of the source frame rate — 0.2 by default, so a 100 fps clip gives
   20 frames a second. **Absolute** is a number you type.

   The **capture preset** — orbit drone, handheld walk, turntable, interior scan
   — sets both the target frame count and how much movement between frames is
   healthy, because those are two views of the same question: how fast is the
   camera travelling?

   When it finishes you get a gallery of every frame with its verdict, a
   sharpness timeline with scene cuts marked, and the ability to overrule any
   verdict by hand. **Re-analyse** re-runs the scoring alone with new
   thresholds — it never re-extracts.

3. **Align.** RealityScan solves the camera positions and produces a sparse
   point cloud, rendered in the viewer with the camera path drawn through it.

   Alignment is the step that fails most interestingly. If it splits the scene
   into unrelated pieces, the app keeps the largest and **tells you** — it
   reports how many of your frames came back with a pose and which ones did not,
   and the viewer marks the edges of each hole in the camera path. It does not
   fail the step over it: a handful of unalignable frames should not stop the
   pipeline, and whether to re-align is your call.

4. **Train.** LichtFeld Studio trains the splat, streaming its progress into the
   live log. Long step. It can be aborted, and aborting genuinely kills the
   process tree — it will not leave anything holding your GPU.

5. **Export.** The trained splat is written to `export/` and shown in the
   viewer.

6. **Blender scene.** Optional. Builds a `.blend` around the exported splat,
   ready for the [SplatForge](https://github.com/ymgenesis/SplatForge-for-Blender)
   add-on if you want to relight or composite it.

### Reading the viewer

Steps 3 to 5 render in-app. Nothing loads the raw output — a sparse cloud is
routinely over a hundred megabytes and a trained splat can pass a gigabyte, so
the backend writes a decimated, browser-sized copy first. The detail level is a
control in the viewer, and **Full** always loads the whole thing.

Two things worth knowing:

- The decimation is an even spread across the file, never the first N points.
  A point cloud is not shuffled — its first million points are one corner of
  the scene, not a preview of it.
- **Flip up** turns the whole view over. The alignment step defines "up" from
  the scene it solved, which is not always the vertical you had in mind.

---

## 6. Where your data lives

Everything belonging to a project sits in one directory:

```
projects/<project-slug>/
├── input/       the source video
├── frames/      the extracted frames
├── analysis/    the curation results: scores, verdicts, your overrides
├── report/      the quality report
├── rc_output/   camera solution + sparse cloud
├── lfs_output/  the trained splat
├── export/      the final files, and the Blender scene
└── preview/     browser-sized copies for the viewer — a cache, safe to delete
```

`projects/` is yours. No script in this repository deletes it, cleans it or
resets it.

---

## 7. Managing projects

Every project tile carries a `⋮` menu:

| Option | What it does |
|---|---|
| **Copy** | duplicates the whole project under a new name, wizard position and settings included |
| **Reset** | deletes the output of one step **and of every step after it**, then rewinds the wizard — `input/` is always kept |
| **Archive** | zips the project away and keeps the row in the list, disabled, until you restore it |
| **Delete** | removes the project, its directory and its archive |

Reset takes the later steps with it because their output was computed from what
is being deleted; leaving them would show you the previous run's result next to
an empty directory.

All four are refused while that project has a job running, and all four run
behind a dialog that cannot be dismissed. That is deliberate: a copy moves
gigabytes file by file and **there is nothing to abort it with** — unlike a
pipeline step, there is no child process to kill. Starting something else on top
of it would leave a half-written directory, not a queue.

---

## 8. When something goes wrong

| Symptom | Cause |
|---|---|
| A step fails naming a path | that tool's path in `config.json` is wrong or empty. The error quotes the exact path it tried |
| The frontend loads but nothing works | the backend is not running. Both servers are needed; check the Backend console window |
| Port already in use | a previous run is still alive. Close its console window, or kill the process holding 8000 / 5173 |
| Training "succeeds" but there is no output | check the live log for a training error. The app already fails the step when its output directory has no splat in it — a zero exit code from the trainer is not taken as success |
| A wall of CUDA `driver shutting down` messages at the end of training | normal shutdown noise, not a failure |
| The viewer shows the previous run's cloud | `preview/` is a cache keyed on the source file. Deleting the directory costs one rebuild |

The **live log** at the bottom of the wizard carries the tools' own output, with
their errors and warnings marked. It is the first place to look, and usually the
last.

---

## Licence

Application code: see the repository. Third-party dependencies are audited in
[CLAUDE.md §10](../CLAUDE.md). FFmpeg, RealityScan, LichtFeld Studio and Blender
are called as subprocesses under their own licences and are never bundled here.
