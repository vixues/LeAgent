import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Box } from 'lucide-react';

import { cn } from '@/lib/utils';
import { useChatFileBlobUrl } from '@/hooks/useChatFileBlobUrl';
import {
  extractApiFilePreviewId,
  isInvalidApiFilePreviewRef,
  managedFilePreviewHasSignedToken,
} from '@/components/chat/media/chatMediaUtils';

export interface CanvasMesh3DPreviewHandle {
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
}

function useModelUrl(previewUrl?: string, fileId?: string): { url?: string; loading: boolean } {
  const raw = previewUrl || (fileId ? `/api/v1/files/${fileId}/preview` : '');
  const invalid = useMemo(() => isInvalidApiFilePreviewRef(raw), [raw]);
  const managedId = useMemo(
    () => (invalid ? null : extractApiFilePreviewId(raw)),
    [raw, invalid],
  );
  const signed = useMemo(() => managedFilePreviewHasSignedToken(raw), [raw]);
  const { blobUrl, isLoading } = useChatFileBlobUrl(managedId);
  const trimmed = raw.trim();
  const url = useMemo(() => {
    if (invalid) return undefined;
    if (!managedId) return trimmed || undefined;
    if (blobUrl) return blobUrl;
    if (signed && trimmed) return trimmed;
    return undefined;
  }, [invalid, managedId, blobUrl, signed, trimmed]);
  return { url, loading: Boolean(managedId) && isLoading && !url };
}

/** Frame camera so the whole model is centered and visible in the viewport. */
function frameModel(
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
  root: THREE.Object3D,
  padding = 1.2,
) {
  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty()) return;

  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z, 0.001);

  const fovRad = (camera.fov * Math.PI) / 180;
  const fitHeight = maxDim / (2 * Math.tan(fovRad / 2));
  const fitWidth = fitHeight / Math.max(camera.aspect, 0.01);
  const distance = padding * Math.max(fitHeight, fitWidth);

  let dir = camera.position.clone().sub(controls.target);
  if (dir.lengthSq() < 1e-6) {
    dir = new THREE.Vector3(0.35, 0.25, 1);
  }
  dir.normalize();

  controls.target.copy(center);
  camera.position.copy(center.clone().add(dir.multiplyScalar(distance)));
  camera.near = Math.max(0.01, distance / 100);
  camera.far = Math.max(200, distance * 20);
  camera.updateProjectionMatrix();
  controls.update();
}

function centerModelAtOrigin(root: THREE.Object3D) {
  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  root.position.sub(center);
}

/** Compact inline GLB viewer with zoom / fit controls for workflow canvas assets. */
export const CanvasMesh3DPreview = forwardRef<
  CanvasMesh3DPreviewHandle,
  {
    previewUrl?: string;
    fileId?: string;
    autoRotate?: boolean;
    className?: string;
    height?: number;
  }
>(function CanvasMesh3DPreview(
  { previewUrl, fileId, className, height = 160, autoRotate },
  ref,
) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const modelRef = useRef<THREE.Object3D | null>(null);
  const { url, loading } = useModelUrl(previewUrl, fileId);
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const rotate = autoRotate !== false;

  useImperativeHandle(ref, () => ({
    zoomIn: () => {
      const camera = cameraRef.current;
      const controls = controlsRef.current;
      if (!camera || !controls) return;
      const dir = camera.position.clone().sub(controls.target).normalize();
      const dist = camera.position.distanceTo(controls.target) * 0.82;
      camera.position.copy(controls.target.clone().add(dir.multiplyScalar(dist)));
      controls.update();
    },
    zoomOut: () => {
      const camera = cameraRef.current;
      const controls = controlsRef.current;
      if (!camera || !controls) return;
      const dir = camera.position.clone().sub(controls.target).normalize();
      const dist = camera.position.distanceTo(controls.target) * 1.22;
      camera.position.copy(controls.target.clone().add(dir.multiplyScalar(dist)));
      controls.update();
    },
    fitView: () => {
      const camera = cameraRef.current;
      const controls = controlsRef.current;
      const model = modelRef.current;
      if (!camera || !controls || !model) return;
      frameModel(camera, controls, model);
    },
  }));

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !url) {
      setStatus(url ? 'loading' : 'idle');
      return;
    }

    let disposed = false;
    setStatus('loading');

    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#000000');
    const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 200);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.autoRotate = rotate;
    controls.autoRotateSpeed = 1.2;
    controlsRef.current = controls;

    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const key = new THREE.DirectionalLight(0xffffff, 0.95);
    key.position.set(3, 4, 5);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0x93c5fd, 0.35);
    fill.position.set(-2, 1, -3);
    scene.add(fill);

    const loader = new GLTFLoader();
    let modelRoot: THREE.Object3D | null = null;

    loader.load(
      url,
      (gltf) => {
        if (disposed) return;
        modelRoot = gltf.scene;
        centerModelAtOrigin(modelRoot);
        scene.add(modelRoot);
        modelRef.current = modelRoot;
        frameModel(camera, controls, modelRoot);
        setStatus('ready');
      },
      undefined,
      () => {
        if (!disposed) setStatus('error');
      },
    );

    const resize = () => {
      const w = host.clientWidth || 1;
      const h = host.clientHeight || height;
      renderer.setSize(w, h, true);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      if (modelRoot) frameModel(camera, controls, modelRoot);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(host);

    let frame = 0;
    const tick = () => {
      if (disposed) return;
      frame = requestAnimationFrame(tick);
      controls.autoRotate = rotate;
      controls.update();
      renderer.render(scene, camera);
    };
    tick();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      ro.disconnect();
      controls.dispose();
      renderer.dispose();
      cameraRef.current = null;
      controlsRef.current = null;
      modelRef.current = null;
      if (modelRoot) scene.remove(modelRoot);
      if (renderer.domElement.parentNode === host) host.removeChild(renderer.domElement);
    };
  }, [url, height, rotate]);

  if (loading || status === 'loading') {
    return (
      <div
        className={cn('flex items-center justify-center bg-surface-sunken', className)}
        style={{ height }}
      >
        <div className="h-6 w-6 animate-pulse rounded-full bg-muted" />
      </div>
    );
  }

  if (!url || status === 'error') {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center gap-1 bg-surface-sunken text-muted-foreground',
          className,
        )}
        style={{ height }}
      >
        <Box className="h-6 w-6" aria-hidden />
        <span className="text-[10px]">3D preview</span>
      </div>
    );
  }

  return (
    <div
      ref={hostRef}
      className={cn('nodrag w-full overflow-hidden bg-black', className)}
      style={{ height }}
    />
  );
});
