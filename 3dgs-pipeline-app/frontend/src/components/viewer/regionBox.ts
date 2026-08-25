import * as THREE from 'three';
import type { Region } from '@/types';

/**
 * The Reconstruction Region as something the viewer can draw and drag.
 *
 * The box is a unit `BoxGeometry` **scaled** rather than a geometry rebuilt at
 * every size: `TransformControls` in scale mode writes `object.scale`, so the
 * scale *is* the size, and rebuilding the geometry underneath a live gizmo
 * fights it.
 *
 * ### Frames — three of them, and only one belongs on the wire
 *
 * * the **app frame** is the NeRF one (`rc_region.py`), which is what
 *   `/api/projects/{id}/region` speaks in both directions;
 * * the **cloud frame** is whatever `pointcloud.ply` is actually in — the same
 *   NeRF frame after `rc_postprocess`, but RealityScan's own Z-up frame on a
 *   project aligned with `rc.normalise_for_lfs` off. The preview is a copy of
 *   that file, so this is the frame the box must be drawn in to sit on it;
 * * the **display** rotation of `frame.ts` (`Rx+180`, plus the "Flip up"
 *   toggle) is applied to the *parent group*, exactly as it is to the cloud, so
 *   the box inherits it and the numbers underneath never see it.
 *
 * Hence: the group carries the display flip, the box's own local transform is
 * the cloud frame, and `toApp` / `fromApp` are the only conversion — a no-op
 * whenever the cloud is normalised, which is every project that has not turned
 * the normalisation off.
 */

export interface RegionBoxHandle {
  group: THREE.Group;
  mesh: THREE.Mesh;
  edges: THREE.LineSegments;
  dispose(): void;
}

/** Euler order of the app's `euler_deg` triple — see `rc_region.euler_to_matrix`. */
export const EULER_ORDER = 'ZYX' as const;

const DEG = Math.PI / 180;

/** `Rx+90`: RealityScan's native Z-up onto the app's NeRF frame. */
const RC_TO_NERF = new THREE.Matrix4().makeRotationX(Math.PI / 2);
const NERF_TO_RC = new THREE.Matrix4().makeRotationX(-Math.PI / 2);

function convert(region: Region, matrix: THREE.Matrix4, frame: Region['frame']): Region {
  const centre = new THREE.Vector3(...region.centre).applyMatrix4(matrix);
  const rotation = new THREE.Matrix4().makeRotationFromEuler(
    new THREE.Euler(
      region.euler_deg[0] * DEG, region.euler_deg[1] * DEG, region.euler_deg[2] * DEG,
      EULER_ORDER,
    ),
  );
  const basis = new THREE.Matrix4().extractRotation(matrix).multiply(rotation);
  const euler = new THREE.Euler().setFromRotationMatrix(basis, EULER_ORDER);
  return {
    ...region,
    // The label moves with the values. Leaving it saying "nerf" on a box that
    // has just been rotated into RealityScan's frame is precisely the mistake
    // this module exists to make impossible.
    frame,
    centre: [centre.x, centre.y, centre.z],
    euler_deg: [euler.x / DEG, euler.y / DEG, euler.z / DEG],
  };
}

/** App (NeRF) frame -> the frame the loaded cloud is in. */
export function toCloudFrame(region: Region, cloudFrame: string): Region {
  return cloudFrame === 'rc' ? convert(region, NERF_TO_RC, 'rc') : region;
}

/** The frame the loaded cloud is in -> the app (NeRF) frame, for the PUT. */
export function toAppFrame(region: Region, cloudFrame: string): Region {
  return cloudFrame === 'rc' ? convert(region, RC_TO_NERF, 'nerf') : region;
}

/**
 * A transparent box with a hard edge overlay, in a group the caller flips.
 *
 * Two objects because one cannot do both jobs: a translucent solid says where
 * the volume is and hides nothing behind it, while the edges are what stays
 * readable once the box is bigger than the screen.
 */
export function buildRegionBox(colour = 0x22d3ee): RegionBoxHandle {
  const group = new THREE.Group();
  const geometry = new THREE.BoxGeometry(1, 1, 1);

  const material = new THREE.MeshBasicMaterial({
    color: colour,
    transparent: true,
    opacity: 0.08,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const mesh = new THREE.Mesh(geometry, material);
  // The box is routinely larger than the scene; three.js would cull it the
  // moment its centre left the frustum, which is exactly when it is being
  // dragged into place.
  mesh.frustumCulled = false;

  const edgeGeometry = new THREE.EdgesGeometry(geometry);
  const edgeMaterial = new THREE.LineBasicMaterial({ color: colour, depthTest: false });
  const edges = new THREE.LineSegments(edgeGeometry, edgeMaterial);
  edges.frustumCulled = false;
  // Drawn last so the edges read through the cloud rather than fighting it.
  edges.renderOrder = 2;
  mesh.add(edges);

  group.add(mesh);

  return {
    group,
    mesh,
    edges,
    dispose() {
      geometry.dispose();
      material.dispose();
      edgeGeometry.dispose();
      edgeMaterial.dispose();
      group.remove(mesh);
    },
  };
}

/** Push a region (already in the cloud frame) onto the mesh. */
export function applyRegion(mesh: THREE.Mesh, region: Region): void {
  mesh.position.set(region.centre[0], region.centre[1], region.centre[2]);
  mesh.rotation.set(
    region.euler_deg[0] * DEG, region.euler_deg[1] * DEG, region.euler_deg[2] * DEG,
    EULER_ORDER,
  );
  mesh.scale.set(
    Math.max(region.size[0], 1e-6),
    Math.max(region.size[1], 1e-6),
    Math.max(region.size[2], 1e-6),
  );
  mesh.updateMatrixWorld(true);
}

/** Read the mesh back — the inverse of `applyRegion`, in the cloud frame. */
export function readRegion(mesh: THREE.Mesh, template: Region): Region {
  const euler = new THREE.Euler().setFromQuaternion(mesh.quaternion, EULER_ORDER);
  return {
    ...template,
    centre: [mesh.position.x, mesh.position.y, mesh.position.z],
    // A gizmo can drag a scale through zero and out the other side; a box with
    // a negative side is not a box, and RS would read the absolute value anyway.
    size: [Math.abs(mesh.scale.x), Math.abs(mesh.scale.y), Math.abs(mesh.scale.z)],
    euler_deg: [euler.x / DEG, euler.y / DEG, euler.z / DEG],
  };
}

/**
 * How many of `positions` sit inside the box — the live number under the viewer.
 *
 * Counted in the box's own axes: a point is inside when all three of its
 * coordinates in that basis are within half a side. Same test as
 * `rc_region._inside_mask`, so the browser's number and the one written into
 * `region.json` are the same number.
 *
 * `positions` is the interleaved `Float32Array` the preview was parsed into,
 * and it is in the cloud frame — the same one `region` must be in.
 */
export function countInside(positions: Float32Array, region: Region): number {
  const inverse = new THREE.Matrix4()
    .makeRotationFromEuler(new THREE.Euler(
      region.euler_deg[0] * DEG, region.euler_deg[1] * DEG, region.euler_deg[2] * DEG,
      EULER_ORDER,
    ))
    .setPosition(region.centre[0], region.centre[1], region.centre[2])
    .invert();

  const hx = Math.abs(region.size[0]) / 2;
  const hy = Math.abs(region.size[1]) / 2;
  const hz = Math.abs(region.size[2]) / 2;
  if (hx <= 0 || hy <= 0 || hz <= 0) return 0;

  const e = inverse.elements;
  let inside = 0;
  for (let i = 0; i < positions.length; i += 3) {
    const x = positions[i];
    const y = positions[i + 1];
    const z = positions[i + 2];
    const lx = e[0] * x + e[4] * y + e[8] * z + e[12];
    if (lx < -hx || lx > hx) continue;
    const ly = e[1] * x + e[5] * y + e[9] * z + e[13];
    if (ly < -hy || ly > hy) continue;
    const lz = e[2] * x + e[6] * y + e[10] * z + e[14];
    if (lz < -hz || lz > hz) continue;
    inside += 1;
  }
  return inside;
}

/** A percentile-bounds fit of the loaded cloud — "Fit to cloud", in the browser.
 *
 *  Percentile and not min/max, for the reason `rc_region.region_from_pointcloud`
 *  gives: one stray point 400 m out otherwise defines the whole box, and an RS
 *  sparse cloud always has a few.
 */
export function fitToCloud(positions: Float32Array, percentile = 1.0): {
  centre: [number, number, number];
  size: [number, number, number];
} | null {
  const n = Math.floor(positions.length / 3);
  if (n === 0) return null;

  const centre: number[] = [];
  const size: number[] = [];
  for (let axis = 0; axis < 3; axis += 1) {
    const values = new Float32Array(n);
    for (let i = 0; i < n; i += 1) values[i] = positions[i * 3 + axis];
    values.sort();
    const lo = values[Math.min(n - 1, Math.floor((percentile / 100) * (n - 1)))];
    const hi = values[Math.max(0, Math.ceil((1 - percentile / 100) * (n - 1)))];
    centre.push((hi + lo) / 2);
    size.push(Math.max(hi - lo, 1e-6));
  }
  return {
    centre: [centre[0], centre[1], centre[2]],
    size: [size[0], size[1], size[2]],
  };
}
