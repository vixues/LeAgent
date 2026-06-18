import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

import { cn } from '@/lib/utils';

import {
  AZIMUTH_PRESETS,
  DISTANCE_PRESETS,
  ELEVATION_PRESETS,
} from './cameraAngles';

export interface MultiAngleCameraState {
  horizontalAngle: number;
  verticalAngle: number;
  zoom: number;
}

interface MultiAngleCameraViewportProps {
  imageUrl?: string;
  meshUrl?: string;
  horizontalAngle: number;
  verticalAngle: number;
  zoom: number;
  cameraView?: boolean;
  className?: string;
  height?: number;
  /** Scales the preview card / subject in the scene (0.5–2). */
  subjectScale?: number;
  onChange: (next: MultiAngleCameraState) => void;
}

function clampElevation(v: number): number {
  return Math.max(-30, Math.min(60, v));
}

/** Distance so a plane of ``planeSize`` fits in the camera frustum at given aspect. */
function fitDistanceForPlane(
  camera: THREE.PerspectiveCamera,
  planeSize: number,
  padding = 1.35,
): number {
  const fovRad = (camera.fov * Math.PI) / 180;
  const fitH = planeSize / (2 * Math.tan(fovRad / 2));
  const fitW = fitH / Math.max(camera.aspect, 0.01);
  return padding * Math.max(fitH, fitW);
}

function setCameraFromAngles(
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
  h: number,
  v: number,
  zoom: number,
  subjectRadius: number,
) {
  const baseDist = fitDistanceForPlane(camera, subjectRadius * 2);
  const zoomFactor = 0.35 + (1 - Math.max(0, Math.min(10, zoom)) / 10) * 0.85;
  const dist = baseDist * zoomFactor;

  const az = (h * Math.PI) / 180;
  const el = (clampElevation(v) * Math.PI) / 180;
  const x = dist * Math.cos(el) * Math.sin(az);
  const y = dist * Math.sin(el);
  const z = dist * Math.cos(el) * Math.cos(az);
  camera.position.set(x, y, z);
  controls.target.set(0, 0, 0);
  camera.near = Math.max(0.01, dist / 200);
  camera.far = Math.max(100, dist * 30);
  camera.updateProjectionMatrix();
  controls.update();
}

function readAnglesFromCamera(
  camera: THREE.PerspectiveCamera,
  subjectRadius: number,
): MultiAngleCameraState {
  const { x, y, z } = camera.position;
  const dist = Math.sqrt(x * x + y * y + z * z) || 1;
  const az = ((Math.atan2(x, z) * 180) / Math.PI + 360) % 360;
  const el = clampElevation((Math.asin(y / dist) * 180) / Math.PI);
  const baseDist = fitDistanceForPlane(camera, subjectRadius * 2);
  const zoomFactor = dist / Math.max(baseDist, 0.001);
  const zoom = Math.round((1 - (zoomFactor - 0.35) / 0.85) * 10 * 10) / 10;
  return {
    horizontalAngle: Math.round(az),
    verticalAngle: Math.round(el),
    zoom: Math.max(0, Math.min(10, zoom)),
  };
}

function boundingRadius(root: THREE.Object3D, scale = 0.55): number {
  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty()) return 0.75;
  const size = box.getSize(new THREE.Vector3());
  return Math.max(size.x, size.y, size.z, 0.001) * scale;
}

function centerModelAtOrigin(root: THREE.Object3D) {
  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  root.position.sub(center);
}

function disposeObject3D(root: THREE.Object3D) {
  root.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      child.geometry?.dispose();
      const mats = Array.isArray(child.material) ? child.material : [child.material];
      mats.forEach((mat) => mat?.dispose());
    }
  });
}

function updateRingForSubject(ring: THREE.Mesh, root: THREE.Object3D, fallbackY = -0.72) {
  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty()) {
    ring.position.y = fallbackY;
    ring.scale.set(1, 1, 1);
    return;
  }
  const size = box.getSize(new THREE.Vector3());
  const ringR = Math.max(size.x, size.z, 0.4) * 0.72;
  ring.scale.set(ringR, ringR, 1);
  ring.position.y = box.min.y - 0.02;
}

/** Interactive multi-angle camera viewport (ComfyUI-qwenmultiangle style). */
export function MultiAngleCameraViewport({
  imageUrl,
  meshUrl,
  horizontalAngle,
  verticalAngle,
  zoom,
  cameraView = false,
  className,
  height = 200,
  subjectScale = 1,
  onChange,
}: MultiAngleCameraViewportProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const propsRef = useRef({
    horizontalAngle,
    verticalAngle,
    zoom,
    imageUrl,
    meshUrl,
    subjectScale,
    height,
    cameraView,
  });
  propsRef.current = {
    horizontalAngle,
    verticalAngle,
    zoom,
    imageUrl,
    meshUrl,
    subjectScale,
    height,
    cameraView,
  };

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let disposed = false;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#000000');
    scene.fog = new THREE.Fog('#000000', 8, 28);

    const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 200);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.1;
    controls.enablePan = false;
    controls.minDistance = 0.8;
    controls.maxDistance = 24;

    const grid = new THREE.GridHelper(6, 24, '#3b4f6b', '#1a2435');
    grid.position.y = -0.72;
    scene.add(grid);

    const subject = new THREE.Group();
    scene.add(subject);

    const cardGeo = new THREE.PlaneGeometry(1, 1);
    const cardMat = new THREE.MeshStandardMaterial({
      color: '#475569',
      side: THREE.DoubleSide,
      roughness: 0.72,
      metalness: 0.04,
    });
    const card = new THREE.Mesh(cardGeo, cardMat);
    subject.add(card);

    const modelHolder = new THREE.Group();
    subject.add(modelHolder);

    const backMat = new THREE.MeshStandardMaterial({
      color: '#1e293b',
      side: THREE.BackSide,
      roughness: 0.9,
    });
    const cardBack = new THREE.Mesh(cardGeo, backMat);
    cardBack.position.z = -0.002;
    subject.add(cardBack);

    const frame = new THREE.LineSegments(
      new THREE.EdgesGeometry(cardGeo),
      new THREE.LineBasicMaterial({ color: '#94a3b8', transparent: true, opacity: 0.55 }),
    );
    subject.add(frame);

    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(1, 0.018, 8, 72),
      new THREE.MeshBasicMaterial({ color: '#f472b6', transparent: true, opacity: 0.85 }),
    );
    ring.rotation.x = Math.PI / 2;
    ring.position.y = -0.72;
    subject.add(ring);

    const camMarker = new THREE.Mesh(
      new THREE.ConeGeometry(0.09, 0.22, 8),
      new THREE.MeshBasicMaterial({ color: '#fbbf24' }),
    );
    scene.add(camMarker);

    scene.add(new THREE.AmbientLight(0xffffff, 0.5));
    const key = new THREE.DirectionalLight(0xffffff, 1.0);
    key.position.set(3, 5, 4);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0x7dd3fc, 0.35);
    fill.position.set(-4, 2, -2);
    scene.add(fill);
    const rim = new THREE.DirectionalLight(0xf9a8d4, 0.25);
    rim.position.set(0, -2, -4);
    scene.add(rim);

    let texture: THREE.Texture | null = null;
    const textureLoader = new THREE.TextureLoader();
    const gltfLoader = new GLTFLoader();
    let syncing = false;
    let cardBaseW = 1.35;
    let cardBaseH = 1.35;
    let subjectRadius = cardBaseW * 0.55;
    let loadedMesh: THREE.Object3D | null = null;

    const setImagePlaneVisible = (visible: boolean) => {
      card.visible = visible;
      cardBack.visible = visible;
      frame.visible = visible;
    };

    const applyCardSize = (baseW: number, baseH: number, scale: number) => {
      cardBaseW = baseW;
      cardBaseH = baseH;
      const w = baseW * scale;
      const h = baseH * scale;
      subjectRadius = Math.max(w, h) * 0.55;
      card.scale.set(w, h, 1);
      cardBack.scale.set(w, h, 1);
      frame.scale.set(w, h, 1);
      const ringR = Math.max(w, h) * 0.72;
      ring.scale.set(ringR, ringR, 1);
      ring.position.y = -0.72;
    };

    const syncCamera = () => {
      const p = propsRef.current;
      syncing = true;
      setCameraFromAngles(
        camera,
        controls,
        p.horizontalAngle,
        p.verticalAngle,
        p.zoom,
        subjectRadius,
      );
      syncing = false;
    };

    const clearMesh = () => {
      if (loadedMesh) {
        modelHolder.remove(loadedMesh);
        disposeObject3D(loadedMesh);
        loadedMesh = null;
      }
      modelHolder.clear();
    };

    const applyMesh = () => {
      const url = propsRef.current.meshUrl;
      if (!url) {
        clearMesh();
        setImagePlaneVisible(true);
        if (propsRef.current.imageUrl) {
          applyTexture();
        } else {
          applyCardSize(1.35, 1.35, propsRef.current.subjectScale);
          syncCamera();
        }
        return;
      }

      setImagePlaneVisible(false);
      if (loadedMesh && loadedMesh.userData.sourceUrl === url) {
        subjectRadius = boundingRadius(loadedMesh) * propsRef.current.subjectScale;
        updateRingForSubject(ring, loadedMesh);
        syncCamera();
        return;
      }

      clearMesh();
      gltfLoader.load(
        url,
        (gltf) => {
          if (disposed || propsRef.current.meshUrl !== url) {
            disposeObject3D(gltf.scene);
            return;
          }
          const model = gltf.scene;
          model.userData.sourceUrl = url;
          centerModelAtOrigin(model);
          modelHolder.add(model);
          loadedMesh = model;
          subjectRadius = boundingRadius(model) * propsRef.current.subjectScale;
          updateRingForSubject(ring, model);
          syncCamera();
        },
        undefined,
        () => {
          if (!disposed) {
            clearMesh();
            setImagePlaneVisible(true);
            applyTexture();
          }
        },
      );
    };

    const applyTexture = () => {
      if (propsRef.current.meshUrl) return;
      const url = propsRef.current.imageUrl;
      if (!url) {
        texture?.dispose();
        texture = null;
        cardMat.map = null;
        cardMat.color.set('#475569');
        cardMat.needsUpdate = true;
        applyCardSize(1.35, 1.35, propsRef.current.subjectScale);
        syncCamera();
        return;
      }
      textureLoader.load(url, (tex) => {
        if (disposed) {
          tex.dispose();
          return;
        }
        texture?.dispose();
        texture = tex;
        tex.colorSpace = THREE.SRGBColorSpace;
        cardMat.map = tex;
        cardMat.color.set('#ffffff');
        cardMat.needsUpdate = true;

        const img = tex.image as { width?: number; height?: number } | undefined;
        const iw = img?.width && img.width > 0 ? img.width : 1;
        const ih = img?.height && img.height > 0 ? img.height : 1;
        const aspect = iw / ih;
        const base = 1.35;
        const w = aspect >= 1 ? base : base * aspect;
        const h = aspect >= 1 ? base / aspect : base;
        applyCardSize(w, h, propsRef.current.subjectScale);
        syncCamera();
      });
    };

    applyCardSize(1.35, 1.35, subjectScale);
    applyMesh();

    const onControlEnd = () => {
      if (syncing || disposed) return;
      onChangeRef.current(readAnglesFromCamera(camera, subjectRadius));
    };
    controls.addEventListener('end', onControlEnd);

    const resize = () => {
      const w = host.clientWidth || 1;
      const h = host.clientHeight || propsRef.current.height;
      // Update both drawing buffer and canvas CSS size to avoid blur from CSS scaling.
      renderer.setSize(w, h, true);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      syncCamera();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(host);

    let lastUrl = imageUrl;
    let lastMeshUrl = meshUrl;
    let lastScale = subjectScale;
    let animFrame = 0;
    const tick = () => {
      if (disposed) return;
      animFrame = requestAnimationFrame(tick);
      const p = propsRef.current;

      if (p.meshUrl !== lastMeshUrl) {
        lastMeshUrl = p.meshUrl;
        applyMesh();
      } else if (p.imageUrl !== lastUrl) {
        lastUrl = p.imageUrl;
        if (!p.meshUrl) applyTexture();
      }
      if (p.subjectScale !== lastScale) {
        lastScale = p.subjectScale;
        if (loadedMesh) {
          subjectRadius = boundingRadius(loadedMesh) * p.subjectScale;
          updateRingForSubject(ring, loadedMesh);
        } else {
          applyCardSize(cardBaseW, cardBaseH, p.subjectScale);
        }
        syncCamera();
      }

      if (!syncing) {
        const cur = readAnglesFromCamera(camera, subjectRadius);
        if (
          Math.abs(cur.horizontalAngle - p.horizontalAngle) > 1 ||
          Math.abs(cur.verticalAngle - p.verticalAngle) > 1 ||
          Math.abs(cur.zoom - p.zoom) > 0.15
        ) {
          syncCamera();
        }
      }

      // ``cameraView`` toggles between the rig/debug view (grid + ring +
      // camera marker visible) and the clean framed "shot" the configured
      // camera sees (rig helpers hidden so only the subject is composed).
      const rigVisible = !p.cameraView;
      grid.visible = rigVisible;
      ring.visible = rigVisible;
      camMarker.visible = rigVisible;
      scene.fog = rigVisible ? new THREE.Fog('#000000', 8, 28) : null;

      camMarker.position.copy(camera.position);
      camMarker.lookAt(controls.target);
      controls.update();
      renderer.render(scene, camera);
    };
    tick();

    return () => {
      disposed = true;
      cancelAnimationFrame(animFrame);
      controls.removeEventListener('end', onControlEnd);
      ro.disconnect();
      controls.dispose();
      renderer.dispose();
      clearMesh();
      cardGeo.dispose();
      cardMat.dispose();
      backMat.dispose();
      texture?.dispose();
      if (renderer.domElement.parentNode === host) host.removeChild(renderer.domElement);
    };
  }, [height, imageUrl, meshUrl, subjectScale, cameraView]);

  return (
    <div
      ref={hostRef}
      className={cn(
        'nodrag w-full overflow-hidden rounded-md border border-border/60 bg-black',
        className,
      )}
      style={{ height }}
    />
  );
}

export function CameraAngleSelects({
  horizontalAngle,
  verticalAngle,
  zoom,
  onAzimuthPreset,
  onElevationPreset,
  onDistancePreset,
  labels,
}: {
  horizontalAngle: number;
  verticalAngle: number;
  zoom: number;
  onAzimuthPreset: (degrees: number) => void;
  onElevationPreset: (degrees: number) => void;
  onDistancePreset: (z: number) => void;
  labels: { horizontal: string; vertical: string; distance: string };
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <PresetSelect
        label={labels.horizontal}
        value={String(horizontalAngle)}
        options={AZIMUTH_PRESETS.map((p) => ({ value: String(p.degrees), label: p.label }))}
        onChange={(v) => onAzimuthPreset(Number(v))}
      />
      <PresetSelect
        label={labels.vertical}
        value={String(verticalAngle)}
        options={ELEVATION_PRESETS.map((p) => ({ value: String(p.degrees), label: p.label }))}
        onChange={(v) => onElevationPreset(Number(v))}
      />
      <PresetSelect
        label={labels.distance}
        value={String(zoom)}
        options={DISTANCE_PRESETS.map((p) => ({ value: String(p.zoom), label: p.label }))}
        onChange={(v) => onDistancePreset(Number(v))}
      />
    </div>
  );
}

function PresetSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  const selected = options.some((o) => o.value === value) ? value : options[0]?.value;
  return (
    <label className="flex items-center gap-2">
      <span className="w-14 shrink-0 text-[9px] uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <select
        className="nodrag min-w-0 flex-1 rounded border border-border bg-background px-1.5 py-1 text-[10px]"
        value={selected}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
