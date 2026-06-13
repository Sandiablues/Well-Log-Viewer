import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

export type WbvTrajectoryRenderPoint = {
  station_index?: number;
  md?: number | null;
  tvd?: number | null;
  tvdss?: number | null;
  x?: number | null;
  y?: number | null;
  z?: number | null;
  inclination?: number | null;
  azimuth?: number | null;
  dogleg_severity?: number | null;
  east_departure?: number | null;
  north_departure?: number | null;
};

type WbvAxisRange = {
  min?: number | null;
  max?: number | null;
};

type WbvBoundingBox = {
  x?: WbvAxisRange;
  y?: WbvAxisRange;
  z?: WbvAxisRange;
  md?: WbvAxisRange;
  tvd?: WbvAxisRange;
};

type RendererStatus = 'idle' | 'empty' | 'rendered' | 'error';

export type WbvViewPreset = 'reset' | 'fit' | 'top' | 'side';

type WbvTrajectoryRendererProps = {
  renderPoints: WbvTrajectoryRenderPoint[];
  boundingBox?: WbvBoundingBox;
  depthUnit: string;
  viewerState: string;
  viewPreset?: WbvViewPreset;
  viewCommandId?: number;
};

type ScenePoint = {
  x: number;
  y: number;
  z: number;
  md?: number | null;
  tvd?: number | null;
};

type SceneBox = {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  minZ: number;
  maxZ: number;
};

type CameraPlan = {
  position: THREE.Vector3;
  up: THREE.Vector3;
  target: THREE.Vector3;
  viewHeight: number;
};

const TARGET_WELL_HEIGHT = 5.35;
const MIN_DISPLAY_LATERAL_HALF_SPAN = 0.92;
const MAX_DISPLAY_LATERAL_HALF_SPAN = 1.35;

function finiteNumber(value: number | null | undefined, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function firstFinite(...values: Array<number | null | undefined>): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return null;
}

function scenePointsFromBackend(points: WbvTrajectoryRenderPoint[]): ScenePoint[] {
  return points.map((point) => {
    const east = finiteNumber(point.x ?? point.east_departure, 0);
    const north = finiteNumber(point.y ?? point.north_departure, 0);
    const depth = firstFinite(
      point.tvd,
      point.md,
      point.z !== undefined && point.z !== null ? Math.abs(point.z) : null,
    ) ?? 0;

    return {
      x: east,
      y: -depth,
      z: north,
      md: point.md,
      tvd: point.tvd,
    };
  });
}

function sceneBoxCenter(box: SceneBox): THREE.Vector3 {
  return new THREE.Vector3(
    (box.minX + box.maxX) / 2,
    (box.minY + box.maxY) / 2,
    (box.minZ + box.maxZ) / 2,
  );
}

function sceneBoxSpan(box: SceneBox): { x: number; y: number; z: number; max: number } {
  const x = Math.abs(box.maxX - box.minX);
  const y = Math.abs(box.maxY - box.minY);
  const z = Math.abs(box.maxZ - box.minZ);
  return { x, y, z, max: Math.max(x, y, z) };
}

function createNormalizedPoints(points: ScenePoint[]): THREE.Vector3[] {
  const minX = Math.min(...points.map((point) => point.x));
  const maxX = Math.max(...points.map((point) => point.x));
  const minY = Math.min(...points.map((point) => point.y));
  const maxY = Math.max(...points.map((point) => point.y));
  const minZ = Math.min(...points.map((point) => point.z));
  const maxZ = Math.max(...points.map((point) => point.z));

  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  const centerZ = (minZ + maxZ) / 2;
  const verticalSpan = Math.max(1, Math.abs(maxY - minY));
  const scale = TARGET_WELL_HEIGHT / verticalSpan;

  return points.map((point) => new THREE.Vector3(
    (point.x - centerX) * scale,
    (point.y - centerY) * scale,
    (point.z - centerZ) * scale,
  ));
}

function sceneBoxFor(points: THREE.Vector3[]): SceneBox {
  const minX = Math.min(...points.map((point) => point.x));
  const maxX = Math.max(...points.map((point) => point.x));
  const minY = Math.min(...points.map((point) => point.y));
  const maxY = Math.max(...points.map((point) => point.y));
  const minZ = Math.min(...points.map((point) => point.z));
  const maxZ = Math.max(...points.map((point) => point.z));

  const xSpan = Math.abs(maxX - minX);
  const ySpan = Math.abs(maxY - minY);
  const zSpan = Math.abs(maxZ - minZ);
  const verticalPad = Math.max(0.38, ySpan * 0.075);
  const lateralHalfSpan = Math.max(
    MIN_DISPLAY_LATERAL_HALF_SPAN,
    Math.min(MAX_DISPLAY_LATERAL_HALF_SPAN, ySpan * 0.22),
  );

  return {
    minX: xSpan < 0.05 ? -lateralHalfSpan : minX - lateralHalfSpan * 0.24,
    maxX: xSpan < 0.05 ? lateralHalfSpan : maxX + lateralHalfSpan * 0.24,
    minY: minY - verticalPad,
    maxY: maxY + verticalPad,
    minZ: zSpan < 0.05 ? -lateralHalfSpan : minZ - lateralHalfSpan * 0.24,
    maxZ: zSpan < 0.05 ? lateralHalfSpan : maxZ + lateralHalfSpan * 0.24,
  };
}

function createBoxEdges(box: SceneBox, material: THREE.LineBasicMaterial): THREE.LineSegments {
  const corners = {
    bottomFrontLeft: new THREE.Vector3(box.minX, box.minY, box.maxZ),
    bottomFrontRight: new THREE.Vector3(box.maxX, box.minY, box.maxZ),
    bottomBackRight: new THREE.Vector3(box.maxX, box.minY, box.minZ),
    bottomBackLeft: new THREE.Vector3(box.minX, box.minY, box.minZ),
    topFrontLeft: new THREE.Vector3(box.minX, box.maxY, box.maxZ),
    topFrontRight: new THREE.Vector3(box.maxX, box.maxY, box.maxZ),
    topBackRight: new THREE.Vector3(box.maxX, box.maxY, box.minZ),
    topBackLeft: new THREE.Vector3(box.minX, box.maxY, box.minZ),
  };

  const edgePoints = [
    corners.bottomFrontLeft, corners.bottomFrontRight,
    corners.bottomFrontRight, corners.bottomBackRight,
    corners.bottomBackRight, corners.bottomBackLeft,
    corners.bottomBackLeft, corners.bottomFrontLeft,
    corners.topFrontLeft, corners.topFrontRight,
    corners.topFrontRight, corners.topBackRight,
    corners.topBackRight, corners.topBackLeft,
    corners.topBackLeft, corners.topFrontLeft,
    corners.bottomFrontLeft, corners.topFrontLeft,
    corners.bottomFrontRight, corners.topFrontRight,
    corners.bottomBackRight, corners.topBackRight,
    corners.bottomBackLeft, corners.topBackLeft,
  ];

  return new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(edgePoints), material);
}

function createDepthPlane(box: SceneBox, y: number, material: THREE.LineBasicMaterial): THREE.LineSegments {
  const points = [
    new THREE.Vector3(box.minX, y, box.maxZ), new THREE.Vector3(box.maxX, y, box.maxZ),
    new THREE.Vector3(box.maxX, y, box.maxZ), new THREE.Vector3(box.maxX, y, box.minZ),
    new THREE.Vector3(box.maxX, y, box.minZ), new THREE.Vector3(box.minX, y, box.minZ),
    new THREE.Vector3(box.minX, y, box.minZ), new THREE.Vector3(box.minX, y, box.maxZ),
  ];
  return new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(points), material);
}

function createCrossTick(y: number, material: THREE.LineBasicMaterial): THREE.LineSegments {
  const size = 0.17;
  const points = [
    new THREE.Vector3(-size, y, 0), new THREE.Vector3(size, y, 0),
    new THREE.Vector3(0, y, -size), new THREE.Vector3(0, y, size),
  ];
  return new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(points), material);
}

function createTextSprite(text: string, options?: { color?: string; background?: string; scale?: number }): THREE.Sprite {
  const canvas = document.createElement('canvas');
  canvas.width = 640;
  canvas.height = 160;
  const context = canvas.getContext('2d');

  if (context) {
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.font = '800 32px Inter, Arial, sans-serif';
    context.textBaseline = 'middle';
    context.textAlign = 'center';

    if (options?.background) {
      context.fillStyle = options.background;
      const x = 34;
      const y = 44;
      const width = 572;
      const height = 72;
      const radius = 18;
      context.beginPath();
      context.moveTo(x + radius, y);
      context.lineTo(x + width - radius, y);
      context.quadraticCurveTo(x + width, y, x + width, y + radius);
      context.lineTo(x + width, y + height - radius);
      context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
      context.lineTo(x + radius, y + height);
      context.quadraticCurveTo(x, y + height, x, y + height - radius);
      context.lineTo(x, y + radius);
      context.quadraticCurveTo(x, y, x + radius, y);
      context.closePath();
      context.fill();
    }

    context.shadowColor = 'rgba(111, 211, 255, 0.48)';
    context.shadowBlur = 8;
    context.fillStyle = options?.color ?? '#b9f3ff';
    context.fillText(text, canvas.width / 2, canvas.height / 2);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;

  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
    depthWrite: false,
  });

  const sprite = new THREE.Sprite(material);
  const scale = options?.scale ?? 0.27;
  sprite.scale.set(scale * 4.0, scale, 1);
  return sprite;
}

function formatDepth(value: number | null | undefined, unit: string): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return `— ${unit}`;
  return `${Math.round(value).toLocaleString()} ${unit}`;
}

function representativeTicks(points: WbvTrajectoryRenderPoint[]): Array<{ label: string; ratio: number }> {
  if (points.length === 0) return [];

  const indices = Array.from(new Set([
    0,
    Math.floor((points.length - 1) * 0.25),
    Math.floor((points.length - 1) * 0.5),
    Math.floor((points.length - 1) * 0.75),
    points.length - 1,
  ])).filter((index) => index >= 0 && index < points.length);

  const denominator = Math.max(1, points.length - 1);
  return indices.map((index) => ({
    label: formatDepth(points[index].md ?? points[index].tvd, 'ft'),
    ratio: index / denominator,
  }));
}

function materialList(material: THREE.Material | THREE.Material[] | undefined): THREE.Material[] {
  if (!material) return [];
  return Array.isArray(material) ? material : [material];
}

function cameraPlanFor(preset: WbvViewPreset, box: SceneBox, aspect: number): CameraPlan {
  const center = sceneBoxCenter(box);
  const span = sceneBoxSpan(box);
  const lateralSpan = Math.max(span.x, span.z, 1);
  const fitHeight = Math.max(span.y * 1.34, lateralSpan * 1.38, 7.55);
  const distance = Math.max(18, span.max * 3.5);

  if (preset === 'top') {
    return {
      position: center.clone().add(new THREE.Vector3(0, distance, 0.01)),
      up: new THREE.Vector3(0, 0, -1),
      target: center,
      viewHeight: Math.max(lateralSpan * 1.65, 3.9),
    };
  }

  if (preset === 'side') {
    return {
      position: center.clone().add(new THREE.Vector3(distance, 0, 0.01)),
      up: new THREE.Vector3(0, 1, 0),
      target: center,
      viewHeight: Math.max(span.y * 1.24, 7.05),
    };
  }

  if (preset === 'fit') {
    return {
      position: center.clone().add(new THREE.Vector3(distance * 0.55, distance * 0.24, distance * 0.86)),
      up: new THREE.Vector3(0, 1, 0),
      target: center,
      viewHeight: Math.max(fitHeight, 7.9 / Math.max(0.8, aspect)),
    };
  }

  return {
    position: center.clone().add(new THREE.Vector3(distance * 0.6, distance * 0.32, distance * 0.92)),
    up: new THREE.Vector3(0, 1, 0),
    target: center,
    viewHeight: Math.max(fitHeight * 1.06, 8.1 / Math.max(0.8, aspect)),
  };
}

function applyCameraProjection(camera: THREE.OrthographicCamera, viewHeight: number, aspect: number): void {
  camera.left = -viewHeight * aspect * 0.5;
  camera.right = viewHeight * aspect * 0.5;
  camera.top = viewHeight * 0.5;
  camera.bottom = -viewHeight * 0.5;
  camera.near = 0.1;
  camera.far = 1000;
  camera.updateProjectionMatrix();
}

function applyCameraPlan(
  camera: THREE.OrthographicCamera,
  controls: OrbitControls,
  plan: CameraPlan,
  aspect: number,
): void {
  camera.position.copy(plan.position);
  camera.up.copy(plan.up);
  camera.zoom = 1;
  applyCameraProjection(camera, plan.viewHeight, aspect);
  controls.target.copy(plan.target);
  camera.lookAt(plan.target);
  controls.update();
}

function disposeObject(object: THREE.Object3D): void {
  object.traverse((child: THREE.Object3D) => {
    const materialHolder = child as THREE.Object3D & { material?: THREE.Material | THREE.Material[] };
    const geometryHolder = child as THREE.Object3D & { geometry?: THREE.BufferGeometry };

    geometryHolder.geometry?.dispose();

    materialList(materialHolder.material).forEach((material) => {
      const maybeMapped = material as THREE.Material & { map?: THREE.Texture };
      maybeMapped.map?.dispose();
      material.dispose();
    });
  });
}

export function WellboreTrajectoryRenderer({
  renderPoints,
  boundingBox: _boundingBox,
  depthUnit,
  viewerState,
  viewPreset = 'reset',
  viewCommandId = 0,
}: WbvTrajectoryRendererProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [status, setStatus] = useState<RendererStatus>('idle');
  const runtimeRef = useRef<{ applyPreset: (preset: WbvViewPreset) => void } | null>(null);

  const scenePoints = useMemo(() => scenePointsFromBackend(renderPoints), [renderPoints]);
  const depthTicks = useMemo(() => representativeTicks(renderPoints), [renderPoints]);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;

    runtimeRef.current = null;

    if (!host || !canvas) return undefined;

    if (scenePoints.length < 2) {
      setStatus(scenePoints.length === 0 ? 'empty' : 'error');
      return undefined;
    }

    let renderer: THREE.WebGLRenderer | null = null;
    let controls: OrbitControls | null = null;
    let animationFrame: number | null = null;
    let resizeObserver: ResizeObserver | null = null;

    try {
      const normalizedPoints = createNormalizedPoints(scenePoints);
      const box = sceneBoxFor(normalizedPoints);
      const scene = new THREE.Scene();
      const group = new THREE.Group();
      scene.add(group);

      const camera = new THREE.OrthographicCamera(-5, 5, 5, -5, 0.1, 1000);

      renderer = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance',
      });
      renderer.setClearColor(0x000000, 0);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.enableRotate = true;
      controls.enableZoom = true;
      controls.enablePan = true;
      controls.screenSpacePanning = true;
      controls.rotateSpeed = 0.72;
      controls.zoomSpeed = 0.82;
      controls.panSpeed = 0.72;
      controls.minZoom = 0.35;
      controls.maxZoom = 14;
      controls.mouseButtons = {
        LEFT: THREE.MOUSE.ROTATE,
        MIDDLE: THREE.MOUSE.DOLLY,
        RIGHT: THREE.MOUSE.PAN,
      };
      controls.touches = {
        ONE: THREE.TOUCH.ROTATE,
        TWO: THREE.TOUCH.DOLLY_PAN,
      };

      const boxMaterial = new THREE.LineBasicMaterial({
        color: 0x6fd3ff,
        transparent: true,
        opacity: 0.24,
      });
      group.add(createBoxEdges(box, boxMaterial));

      const planeMaterial = new THREE.LineBasicMaterial({
        color: 0x4ca6cc,
        transparent: true,
        opacity: 0.072,
      });
      const tickMaterial = new THREE.LineBasicMaterial({
        color: 0xc6f6ff,
        transparent: true,
        opacity: 0.26,
      });

      depthTicks.forEach((tick) => {
        const y = box.maxY - (box.maxY - box.minY) * tick.ratio;
        group.add(createDepthPlane(box, y, planeMaterial));
        group.add(createCrossTick(y, tickMaterial));

        const label = createTextSprite(`MD ${tick.label}`, {
          color: '#b9f3ff',
          background: 'rgba(3, 8, 12, 0.58)',
          scale: 0.12,
        });
        label.position.set(box.minX - 0.52, y, box.maxZ + 0.09);
        group.add(label);
      });

      const curve = new THREE.CatmullRomCurve3(normalizedPoints, false, 'catmullrom', 0.02);
      const guideGeometry = new THREE.TubeGeometry(
        curve,
        Math.max(40, Math.min(220, normalizedPoints.length * 2)),
        0.008,
        8,
        false,
      );
      const guideMaterial = new THREE.MeshBasicMaterial({
        color: 0x67d599,
        transparent: true,
        opacity: 0.9,
      });
      group.add(new THREE.Mesh(guideGeometry, guideMaterial));

      const lineGeometry = new THREE.BufferGeometry().setFromPoints(normalizedPoints);
      const lineMaterial = new THREE.LineBasicMaterial({
        color: 0xe7fbff,
        transparent: true,
        opacity: 0.68,
      });
      group.add(new THREE.Line(lineGeometry, lineMaterial));

      const topMarker = new THREE.Mesh(
        new THREE.SphereGeometry(0.026, 16, 16),
        new THREE.MeshBasicMaterial({ color: 0xc6f6ff }),
      );
      topMarker.position.copy(normalizedPoints[0]);
      group.add(topMarker);

      const baseMarker = new THREE.Mesh(
        new THREE.SphereGeometry(0.026, 16, 16),
        new THREE.MeshBasicMaterial({ color: 0x67d599 }),
      );
      baseMarker.position.copy(normalizedPoints[normalizedPoints.length - 1]);
      group.add(baseMarker);

      const topLabel = createTextSprite(`Top ${formatDepth(renderPoints[0]?.md ?? renderPoints[0]?.tvd, depthUnit)}`, {
        color: '#e7fbff',
        background: 'rgba(3, 8, 12, 0.62)',
        scale: 0.12,
      });
      topLabel.position.set(box.maxX + 0.5, normalizedPoints[0].y, box.maxZ + 0.1);
      group.add(topLabel);

      const baseLabel = createTextSprite(`Base ${formatDepth(renderPoints[renderPoints.length - 1]?.md ?? renderPoints[renderPoints.length - 1]?.tvd, depthUnit)}`, {
        color: '#dff8ec',
        background: 'rgba(3, 8, 12, 0.62)',
        scale: 0.12,
      });
      baseLabel.position.set(box.maxX + 0.52, normalizedPoints[normalizedPoints.length - 1].y, box.maxZ + 0.1);
      group.add(baseLabel);

      const xLabel = createTextSprite('X / EAST', { color: '#80dcff', scale: 0.12 });
      xLabel.position.set(box.maxX + 0.34, box.minY, box.maxZ + 0.08);
      group.add(xLabel);

      const yLabel = createTextSprite('Y / NORTH', { color: '#80dcff', scale: 0.12 });
      yLabel.position.set(box.minX - 0.34, box.minY, box.maxZ + 0.08);
      group.add(yLabel);

      const zLabel = createTextSprite('Z / TVD', { color: '#80dcff', scale: 0.13 });
      zLabel.position.set(box.maxX + 0.38, box.maxY, box.minZ - 0.08);
      group.add(zLabel);

      const resizeRenderer = () => {
        if (!renderer) return { width: 1, height: 1, aspect: 1 };
        const width = Math.max(1, host.clientWidth);
        const height = Math.max(1, host.clientHeight);
        const aspect = width / height;
        renderer.setSize(width, height, false);
        return { width, height, aspect };
      };

      const applyPreset = (preset: WbvViewPreset) => {
        if (!controls) return;
        const { aspect } = resizeRenderer();
        const plan = cameraPlanFor(preset, box, aspect);
        applyCameraPlan(camera, controls, plan, aspect);
      };

      const resizeAndPreserveView = () => {
        const { aspect } = resizeRenderer();
        const currentViewHeight = Math.abs(camera.top - camera.bottom) || cameraPlanFor(viewPreset, box, aspect).viewHeight;
        applyCameraProjection(camera, currentViewHeight, aspect);
      };

      runtimeRef.current = { applyPreset };
      resizeRenderer();
      applyPreset(viewPreset);

      const renderScene = () => {
        if (!renderer || !controls) return;
        controls.update();
        renderer.render(scene, camera);
        animationFrame = window.requestAnimationFrame(renderScene);
      };

      resizeObserver = new ResizeObserver(resizeAndPreserveView);
      resizeObserver.observe(host);
      renderScene();
      setStatus('rendered');

      return () => {
        runtimeRef.current = null;
        if (animationFrame !== null) {
          window.cancelAnimationFrame(animationFrame);
        }
        resizeObserver?.disconnect();
        controls?.dispose();
        disposeObject(scene);
        renderer?.dispose();
      };
    } catch (error) {
      console.error('WBV trajectory renderer failed', error);
      runtimeRef.current = null;
      setStatus('error');
      controls?.dispose();
      renderer?.dispose();
      return undefined;
    }
  }, [depthTicks, depthUnit, renderPoints, scenePoints]);

  useEffect(() => {
    runtimeRef.current?.applyPreset(viewPreset);
  }, [viewPreset, viewCommandId]);

  const pointCount = renderPoints.length.toLocaleString();

  return (
    <div
      className="wlv-wbv-trajectory-renderer"
      ref={hostRef}
      aria-label="Backend-owned 3D wellbore trajectory renderer"
      data-renderer-status={status}
      data-viewer-state={viewerState}
    >
      <canvas ref={canvasRef} aria-hidden="true" />
      <div className="wlv-wbv-renderer-readout" aria-live="polite">
        <strong>{status === 'rendered' ? '3D trajectory rendered' : `3D trajectory renderer: ${status}`}</strong>
        <span>{pointCount} backend render points · {depthUnit} · {viewPreset} view</span>
      </div>
    </div>
  );
}
