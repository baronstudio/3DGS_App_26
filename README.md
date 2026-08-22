# 3DGS Pipeline App

A local-first web application that drives a complete **video → 3D Gaussian
Splatting** pipeline, from the raw clip to a Blender scene.

You give it a video. It extracts the frames, throws away the ones that would
hurt the reconstruction, aligns what is left into a camera solution, trains a
Gaussian Splatting model on it, exports the splat and assembles a Blender scene
— each stage a step in a six-step wizard, each step driving a real desktop tool
as a subprocess.

```
video ──▶ extract + curate ──▶ align ──▶ train ──▶ export ──▶ Blender scene
           FFmpeg + OpenCV     RealityScan   LichtFeld Studio
```

> **New to Gaussian Splatting?** It is a way of reconstructing a real scene from
> ordinary photographs or video. Instead of a mesh, the result is a cloud of
> millions of small coloured, oriented ellipsoids — "gaussians" — that render
> the scene in real time from any viewpoint. Getting a good one is mostly a data
> problem: sharp frames, enough overlap between them, and a camera solution that
> holds together. That is what this app is about.

---

## The six steps

| # | Step | Tool | Produces |
|---|---|---|---|
| 1 | **Import** | — | the source video, in the project |
| 2 | **Extract + curate** | FFmpeg, OpenCV, PySceneDetect | frames, minus the blurred and redundant ones |
| 3 | **Align** | RealityScan CLI | camera poses + a sparse point cloud |
| 4 | **Train** | LichtFeld Studio CLI | the trained Gaussian splat |
| 5 | **Export** | — | the final `.ply` / `.splat` |
| 6 | **Blender scene** | Blender + SplatForge | a `.blend` ready to light and render |

Steps 3, 4 and 5 each render their output in an **in-app 3D viewer**. That is
not decoration: an alignment that folded the camera path on itself, or a
training that converged on something other than the scene you shot, is visible
there and almost nowhere else.

### Step 2 is the one that decides the result

Most of a bad splat is decided before any training starts. Step 2 scores every
extracted frame and rejects three kinds of frame automatically:

- **Blurred** — Tenengrad sharpness, judged *relative* to a rolling window of
  its neighbours, never against a fixed threshold that would not survive a
  change of content.
- **Redundant** — frames that barely moved since the last kept one, measured as
  median ORB feature displacement across the frame.
- **Across a cut** — scene changes split the footage into sequences, so the
  overlap logic never compares two unrelated shots.

Everything it decides is visible and reversible: a frame gallery with per-frame
verdicts, a sharpness timeline with cut markers, and a manual keep/drop override
that always wins over the automatic verdict. Thresholds can be re-tuned and the
analysis re-run on its own — changing one number never costs a re-extraction.

---

## Getting started

The application lives in [`3dgs-pipeline-app/`](3dgs-pipeline-app/). Installing
and running it is documented there:

**→ [3dgs-pipeline-app/README.md](3dgs-pipeline-app/README.md)**

In short: Python 3.11+, Node 20+, an NVIDIA GPU, and local installs of
RealityScan, LichtFeld Studio, FFmpeg and Blender. The app never bundles those
— it calls them as subprocesses and needs their paths.

---

## Repository layout

```
.
├── README.md              ← you are here: what the project is
├── DEVELOPING.md          ← architecture, module map, contributor notes
├── CLAUDE.md              ← the specification: every rule and why it exists
├── TODO.md                ← prioritised backlog
├── scripts/               ← local dev tooling
└── 3dgs-pipeline-app/     ← the application
    ├── README.md          ← install, configure, run, use
    ├── backend/           ← FastAPI + the pipeline steps
    ├── frontend/          ← React + Vite wizard
    ├── config.json        ← where your tools are installed
    ├── defaults.json      ← default settings per step
    └── projects/          ← your data — never touched by any clean script
```

## Which document answers which question

| Question | Document |
|---|---|
| What is this, and what does it do? | this file |
| How do I install and run it? | [3dgs-pipeline-app/README.md](3dgs-pipeline-app/README.md) |
| How is it built, and how do I work on it? | [DEVELOPING.md](DEVELOPING.md) |
| Why is it built *that* way? | [CLAUDE.md](CLAUDE.md) — the spec, including a dated decisions log |
| What is coming next? | [TODO.md](TODO.md) |

`CLAUDE.md` is the authority. Where this README simplifies, it simplifies on
purpose; where the two disagree, `CLAUDE.md` is right and this file is a bug.

---

## Scope

This is a **single-user, single-workstation** application by design. There is no
authentication, no job queue and no multi-user mode, and there is no remote or
VPS deployment — it drives GPU-bound Windows binaries that have to be on the
same machine as the browser. One user, one running job at a time.

It is also not an editor. The 3D viewer looks at the pipeline's output; it never
writes to it.

## Licences

The application code is the project's own. Every third-party dependency is
tracked in an audit table in [CLAUDE.md §10](CLAUDE.md) and is permissively
licensed (MIT / BSD / Apache-2.0).

The four desktop tools — **FFmpeg**, **RealityScan**, **LichtFeld Studio** and
**Blender** — are invoked as subprocesses and are never linked or bundled. You
install them yourself, under their own licences.
