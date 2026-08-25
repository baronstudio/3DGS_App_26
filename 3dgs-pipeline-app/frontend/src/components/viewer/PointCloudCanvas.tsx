import React, { useCallback, useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js';
import { buildCameraRig, type CameraRig } from './cameraRig';
import { applyUpFix, upFixPoint } from './frame';
import { fetchWithProgress, parsePointCloud, robustBounds } from './pointCloud';
import {
  applyRegion, buildRegionBox, readRegion, type RegionBoxHandle,
} from './regionBox';
import type { CameraPose, Region } from '@/types';

/**
 * The sparse-cloud renderer: `THREE.Points` over a `PC3D` preview, with the
 * registered cameras drawn on top.
 *
 * Splats get their own canvas (`SplatCanvas`) — a gaussian cloud drawn as
 * points is a different picture, not a cheaper one.
 */

interface PointCloudCanvasProps {
  url: string;
  pointSize: number;
  background: string;
  cameras: CameraPose[] | null;
  showCameras: boolean;
  showPath: boolean;
  /** Draw the cloud 180 deg around X — see `frame.ts`. */
  flipCloud: boolean;
  /** Same for the camera overlay; the two frames are not always the same one. */
  flipCameras: boolean;
  fovX?: number | null;
  aspect?: number | null;
  /** The Reconstruction Region to draw, **in the cloud's frame** (regionBox.ts). */
  region?: Region | null;
  /** Which gizmo is live. `null` draws the box without one. */
  regionMode?: 'translate' | 'rotate' | 'scale' | null;
  /** Every frame of a drag, so the numeric readout follows the gizmo. */
  onRegionChange?: (region: Region) => void;
  /** End of a drag — the moment worth putting in an undo stack or a save. */
  onRegionCommit?: (region: Region) => void;
  /** The parsed positions, for the live inside-count and "Fit to cloud". */
  onPositions?: (positions: Float32Array) => void;
  onLoaded?: (count: number) => void;
  onProgress?: (loaded: number, total: number) => void;
  onError?: (message: string) => void;
}

export const PointCloudCanvas: React.FC<PointCloudCanvasProps> = ({
  url, pointSize, background, cameras, showCameras, showPath,
  flipCloud, flipCameras, fovX, aspect,
  region = null, regionMode = null, onRegionChange, onRegionCommit, onPositions,
  onLoaded, onProgress, onError,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const pointsRef = useRef<THREE.Points | null>(null);
  const rigRef = useRef<CameraRig | null>(null);
  const boxRef = useRef<RegionBoxHandle | null>(null);
  // The box the gizmo is writing into. Read back on every change, so the
  // callbacks below need the shape (frame, source, provenance) that came in.
  const regionRef = useRef<Region | null>(region);
  // Set while a gizmo is being dragged: the effect that pushes `region` onto
  // the mesh must not fight the drag it is echoing.
  const draggingRef = useRef(false);
  // Held in refs, not read from the closure: an inline arrow from the parent
  // changes identity on every render, and a gizmo rebuilt mid-drag drops the
  // drag.
  const onChangeRef = useRef(onRegionChange);
  const onCommitRef = useRef(onRegionCommit);
  onChangeRef.current = onRegionChange;
  onCommitRef.current = onRegionCommit;
  // Framing is the cloud's job, but the cloud arrives asynchronously and the
  // rig may get there first — remember what the cloud decided.
  const framedRef = useRef(false);
  // Kept so flipping the up axis can re-frame: rotating the scene under a
  // camera that stays put swings the subject out of view.
  const boundsRef = useRef<{ centre: number[]; radius: number } | null>(null);

  /** Put a sphere of `radius` around `centre` in view. */
  const frame = useCallback((centre: number[], radius: number) => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) return;
    const target = new THREE.Vector3(centre[0], centre[1], centre[2]);
    const direction = new THREE.Vector3(0.8, 0.5, 1).normalize();
    camera.position.copy(target).addScaledVector(direction, radius * 2.4);
    camera.near = Math.max(radius / 500, 1e-3);
    camera.far = radius * 200;
    camera.updateProjectionMatrix();
    controls.target.copy(target);
    controls.update();
  }, []);

  // ── Renderer, once per mount ───────────────────────────────────────────────
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(55, 1, 0.01, 5000);
    camera.position.set(0, 2, 6);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.domElement.style.display = 'block';
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.rotateSpeed = 0.6;

    sceneRef.current = scene;
    cameraRef.current = camera;
    controlsRef.current = controls;
    rendererRef.current = renderer;

    const resize = () => {
      const { clientWidth, clientHeight } = container;
      if (clientWidth === 0 || clientHeight === 0) return;
      renderer.setSize(clientWidth, clientHeight, false);
      camera.aspect = clientWidth / clientHeight;
      camera.updateProjectionMatrix();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(container);

    let frame = 0;
    const tick = () => {
      frame = requestAnimationFrame(tick);
      controls.update();
      renderer.render(scene, camera);
    };
    tick();

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      sceneRef.current = null;
      cameraRef.current = null;
      controlsRef.current = null;
      rendererRef.current = null;
    };
  }, []);

  // ── Background ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (sceneRef.current) sceneRef.current.background = new THREE.Color(background);
  }, [background]);

  // ── The cloud ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !url) return undefined;

    const abort = new AbortController();
    framedRef.current = false;

    fetchWithProgress(url, (loaded, total) => onProgress?.(loaded, total), abort.signal)
      .then((buffer) => {
        if (abort.signal.aborted) return;
        const cloud = parsePointCloud(buffer);
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.BufferAttribute(cloud.positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(cloud.colors, 3));
        const material = new THREE.PointsMaterial({
          size: pointSize,
          sizeAttenuation: false,
          vertexColors: true,
        });
        const points = new THREE.Points(geometry, material);
        // The bounding sphere three.js would compute is the one the far-flung
        // stray points define, and it frustum-culls the whole cloud the moment
        // you zoom in. The robust bounds below are the honest extent.
        points.frustumCulled = false;

        if (pointsRef.current) {
          scene.remove(pointsRef.current);
          pointsRef.current.geometry.dispose();
          (pointsRef.current.material as THREE.Material).dispose();
        }
        scene.add(points);
        pointsRef.current = points;

        applyUpFix(points, flipCloud);

        const bounds = robustBounds(cloud.positions);
        if (bounds) {
          boundsRef.current = bounds;
          frame(upFixPoint(bounds.centre, flipCloud), bounds.radius);
          framedRef.current = true;
        }
        onPositions?.(cloud.positions);
        onLoaded?.(cloud.count);
      })
      .catch((error: unknown) => {
        if (abort.signal.aborted) return;
        onError?.(error instanceof Error ? error.message : 'Failed to load the preview');
      });

    return () => {
      abort.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  // ── Camera overlay ────────────────────────────────────────────────────────
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return undefined;

    if (rigRef.current) {
      scene.remove(rigRef.current.group);
      rigRef.current.dispose();
      rigRef.current = null;
    }
    if (!showCameras || !cameras || cameras.length === 0) return undefined;

    const rig = buildCameraRig(cameras, { fovX, aspect, showPath });
    if (!rig) return undefined;
    applyUpFix(rig.group, flipCameras);
    scene.add(rig.group);
    rigRef.current = rig;
    // Only when the cloud has not framed the view yet: with a cloud on screen,
    // moving the camera because a checkbox was ticked is disorienting.
    if (!framedRef.current) {
      frame(upFixPoint([rig.centre.x, rig.centre.y, rig.centre.z], flipCameras), rig.radius * 1.4);
      framedRef.current = true;
    }

    return () => {
      if (rigRef.current) {
        scene.remove(rigRef.current.group);
        rigRef.current.dispose();
        rigRef.current = null;
      }
    };
  }, [cameras, showCameras, showPath, flipCameras, fovX, aspect, frame]);

  // -- Up axis ---------------------------------------------------------------
  useEffect(() => {
    if (pointsRef.current) applyUpFix(pointsRef.current, flipCloud);
    const bounds = boundsRef.current;
    if (bounds) frame(upFixPoint(bounds.centre, flipCloud), bounds.radius);
  }, [flipCloud, frame]);


  // ── The Reconstruction Region ─────────────────────────────────────────────
  //
  // The box lives in a group carrying the same display flip as the cloud, so
  // its own local transform is the cloud frame — which is what `readRegion`
  // hands back and what the API is given. Nothing here writes a display
  // rotation into a number that reaches disk.
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !region) return undefined;

    const handle = buildRegionBox();
    applyUpFix(handle.group, flipCloud);
    applyRegion(handle.mesh, region);
    scene.add(handle.group);
    boxRef.current = handle;

    return () => {
      scene.remove(handle.group);
      handle.dispose();
      boxRef.current = null;
    };
    // Built once per mount; `region` and the flip are pushed by the effects
    // below rather than rebuilding the mesh, which would fight a live gizmo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Boolean(region)]);

  useEffect(() => {
    regionRef.current = region;
    const handle = boxRef.current;
    if (!handle || !region || draggingRef.current) return;
    applyRegion(handle.mesh, region);
  }, [region]);

  useEffect(() => {
    if (boxRef.current) applyUpFix(boxRef.current.group, flipCloud);
  }, [flipCloud]);

  // ── The gizmo ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const scene = sceneRef.current;
    const camera = cameraRef.current;
    const renderer = rendererRef.current;
    const controls = controlsRef.current;
    const handle = boxRef.current;
    if (!scene || !camera || !renderer || !controls || !handle || !regionMode) {
      return undefined;
    }

    const gizmo = new TransformControls(camera, renderer.domElement);
    gizmo.setMode(regionMode);
    gizmo.attach(handle.mesh);

    // Without this every drag also orbits the camera, because OrbitControls is
    // listening to the same pointer.
    const onDragging = (event: { value: boolean }) => {
      controls.enabled = !event.value;
      draggingRef.current = event.value;
      if (!event.value && regionRef.current) {
        onCommitRef.current?.(readRegion(handle.mesh, regionRef.current));
      }
    };
    const onChange = () => {
      if (draggingRef.current && regionRef.current) {
        onChangeRef.current?.(readRegion(handle.mesh, regionRef.current));
      }
    };
    gizmo.addEventListener('dragging-changed', onDragging as never);
    gizmo.addEventListener('objectChange', onChange);

    // `TransformControls` extends `Controls`, not `Object3D`, in three 0.169:
    // what goes into the scene is its helper, and adding the controls object
    // itself would put a non-Object3D in the graph.
    const helper = gizmo.getHelper();
    scene.add(helper);

    return () => {
      gizmo.removeEventListener('dragging-changed', onDragging as never);
      gizmo.removeEventListener('objectChange', onChange);
      gizmo.detach();
      scene.remove(helper);
      gizmo.dispose();
      controls.enabled = true;
      draggingRef.current = false;
    };
  }, [regionMode, Boolean(region)]);

  // ── Point size ─────────────────────────────────────────────────────────────

  useEffect(() => {
    const points = pointsRef.current;
    if (points) (points.material as THREE.PointsMaterial).size = pointSize;
  }, [pointSize]);

  return <div ref={containerRef} className="w-full h-full" />;
};

export default PointCloudCanvas;
