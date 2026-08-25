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
| `-setReconstructionRegion <file>` | not measured — it is prompt B that loads one |
| `-exportReconstructionRegion <file>` | `21800`, ~0.02 s |
| `-load <rsproj>` | `20532`, ~0.5 s |
