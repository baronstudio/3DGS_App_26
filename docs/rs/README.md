# `.rsbox` — RealityScan's Reconstruction Region file

Everything here was **exported by the installed RealityScan 2.2**, not written
from documentation. `backend/core/steps/rc_region.py` is written against these
files; SESSION 11 §1.3's sketch of the format was a guess and was wrong in two
places (see below).

All samples come from `projects/fauteuil3d_test`, 251 frames, through its saved
`rc_output/fauteuil3d_test.rsproj` — `-load`, a region verb, then
`-exportReconstructionRegion`.

| File | How it was produced |
|---|---|
| `region_auto.rsbox` | `-setReconstructionRegionAuto` |
| `region_density.rsbox` | `-setReconstructionRegionByDensity` |
| `region_rot_y30.rsbox` | auto, then `-rotateReconstructionRegion 0 30 0` |
| `region_rot_xyz.rsbox` | auto, then `-rotateReconstructionRegion 20 35 50` |
| `region_written_by_app.rsbox` | **written by the app**, through `PUT /api/projects/{id}/region` |
| `region_roundtrip_from_rs.rsbox` | RS's re-export of the line above, after `-setReconstructionRegion` |

The last two are the acceptance test of SESSION 12, run on the real path: the
box was moved, resized and rotated through the API, written to
`region/region.rsbox`, handed back to RealityScan with `-load` +
`-setReconstructionRegion`, and re-exported. Every field matches to ≤ 5e-7 —
including the `ownerId`, which is the component's and therefore changes with
each alignment, so it is preserved from whatever RS last exported rather than
invented.

Note the two files also differ in *shape*: the app writes both triples as
elements, RS answered with `widthHeightDepth` back on the root. Same box.

## The shape

```xml
<ReconstructionRegion globalCoordinateSystem="NONE" globalCoordinateSystemWkt="NONE"
   globalCoordinateSystemName="NONE" isGeoreferenced="0" isLatLon="0"
   yawPitchRoll="0 -0 -36.4972360383387"
   widthHeightDepth="42.9308164458524 46.303498638054 36.9292678833008">
  <Header magic="5395016" version="2"/>
  <CentreEuclid>
    <centre>-7.69872188568115 6.14706659317017 14.2699775695801</centre>
  </CentreEuclid>
  <Residual R="1 0 0 0 1 0 0 0 1" t="0 0 0" s="1" ownerId="{D86E58C1-…}"/>
</ReconstructionRegion>
```

Two corrections to SESSION 11's sketch:

- the centre is **not** on the root — it is `CentreEuclid/centre`;
- `yawPitchRoll` and `widthHeightDepth` are written **either as attributes of
  the root or as child elements**, and both forms came out of the same RS build
  in the same run of six exports (compare `region_rot_y30.rsbox`, which mixes
  them, with `region_auto.rsbox`, which does not). The writer appears to spill
  to elements once the root's attribute line grows. A parser must accept both.

`Residual` was identity in every export measured. It is preserved on write and
never composed — there is no sample to check a non-identity one against.

## `yawPitchRoll` is not `(x, y, z)`

Measured with `-rotateReconstructionRegion`, which the help documents as
rotating the region "around its axes", in degrees:

| Verb | Resulting `yawPitchRoll` |
|---|---|
| `-rotateReconstructionRegion 30 0 0` | `0 -30 -0` |
| `-rotateReconstructionRegion 0 30 0` | `-30 -0 -0` |
| `-rotateReconstructionRegion 0 0 30` | `0 -0 -30` |

So field 1 is a rotation about **Y**, field 2 about **X**, field 3 about **Z**,
all stored negated. The composition order was solved by brute force over the
six orderings against three two-axis runs (`rotX 40` then `rotY 30`; `rotY 30`
then `rotX 40`; `rotZ 30` then `rotX 40`) — exactly one candidate reproduces
all of them to floating point:

```
box-to-world  R = Rz(-roll) · Ry(-yaw) · Rx(-pitch)
```

i.e. `THREE.Euler(-pitch, -yaw, -roll, 'ZYX')`.

## Which region verbs emit a progress task

Measured with `-writeProgress`, and it matters because a verb the plan does not
know about is a phase the step-3 bar sits still through (CLAUDE.md §15.3):

| Verb | Task |
|---|---|
| `-setReconstructionRegionAuto` | **none** |
| `-setReconstructionRegionByDensity` | **none** |
| `-scaleReconstructionRegion` | **none** |
| `-setReconstructionRegion <file>` | **none** — measured in the mask run below |
| `-exportReconstructionRegion <file>` | `21800`, ~0.02 s |
| `-load <rsproj>` | `20532`, ~0.5 s |

## The mask run's verbs (§7.5)

Measured on `publicsemple_truck` (251 images of ~1 Mpx) through its saved
`rc_output/publicsemple_truck.rsproj`, RealityScan 2.2.0.119430.

| Verb | Task | Time | Note |
|---|---|---|---|
| `-load <rsproj>` | `20532` | 0.4 s | |
| `-setReconstructionRegion <file>` | **none** | — | the row above said "not measured"; it is now, and it is silent like its three siblings |
| `-selectAllImages` | **none** | — | |
| `-calculatePreviewModel` | `20560` | 2.3 s | |
| `-calculateNormalModel` / `-calculateHighModel` | `20560` | — | **the same id as preview** — one task for all three qualities |
| `-generateMaskFromMesh` | `62` | 33 s cold, 6 s cached | reports no fraction at all, only `#timeout` heartbeats at `0.00`; renders the mask layer at **half** the image resolution — see below |
| `-exportRegistration <colmap> <params>` | `20576` | 4.3 s | with `colmapExportMasks=1`, writes `masks/` beside `images/` |
| `-exportSelectedModel <obj>` | `6`, `21861` | 0.15 s | not used by the app; measured while checking the mesh was real |
| `-exportMapsAndMask <folder> <params>` | `36` | 0.3 s | **fails**: "Feature not implemented" |
| `-clearCache` after a mesh | — | — | **fails**: "Cache contains current scene modifications. [err:5607]", and pops the crash reporter |

Two things that cost a run each to find out.

**`-exportMapsAndMask` takes both arguments or neither.** Given one, RealityScan
reads it as the params file and answers `err:5617` on a directory. Given both,
it writes `imageList.txt` — so the `ei*` keys recovered from the executable's
string table (`eiExportMasks`, `eiExportDepths`, `eiExportImageList`,
`eiExportFileNaming`, `eiExt`, `eiImageQuality`, `eiReplaceExisting`,
`eiPlaneDistanceUnits`, `eiNear`/`eiFarPlaneDistance`,
`eiExportCameraNormalsFormat`, `eiExportWorldNormalsFormat`,
`eiExportDistanceScale`, `eiExportMasksOrDepths`, `eiExportPhotoconsistencies`)
do reach it — and then fails. The route is not available on this build; §7.5
goes through the COLMAP exporter instead.

**A batch error opens the GUI even under `-headless`.** Both failures above
drew a full-screen red banner over the desktop, and the `err:5607` one launched
the crash reporter as well. Anything the app sends RealityScan has to succeed,
not merely be handled.

## The mask layer is half resolution, and nothing exposed changes that

`-generateMaskFromMesh` writes a mask layer at half the image's linear size —
a 973×543 image gets a 486×271 mask, over all 251 of them. Three things were
tried and none of them moved it:

| Tried | Result |
|---|---|
| `-set "mvsPreviewDownscaleFactor=1"` | still half |
| `-set "txtImageDownscaleColor=1"` | still half |
| `-calculateHighModel` instead of preview | still half |

So it belongs to the mask layer, not to the depth map and not to the mesh. It
is also **proportional**: a 3800 px frame gets a 1900 px mask, so one mask
pixel is always a 2×2 square of image pixels and a bigger source does not
remove the blocking.

The render itself is fine — 189 distinct grey levels, properly anti-aliased,
and its 4×4 and 8×8 blocks are *not* constant, so nothing is quantised below
half. After `rc_alpha.fit_dataset_masks` has doubled it, 99 % of the file's
2×2 blocks are constant and the original recovers exactly as `mask[::2, ::2]`
— that is the signature of the upscale and the way to tell it apart from a
coarse mesh. `INTER_LINEAR` instead of `INTER_NEAREST` is visually
indistinguishable, because LichtFeld Studio thresholds at 0.5 either way.

**One lead is untested**: `ImageDepthMapDownscale` / `inpImageDepthMapDownscale`
is a *per-input* setting in RS's Selected-inputs panel rather than a global
reconstruction one, which would explain why every global key above was a no-op.
