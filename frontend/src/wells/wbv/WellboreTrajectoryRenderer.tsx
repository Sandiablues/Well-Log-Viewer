import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';

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
  const xSpan = Math.abs(maxX - minX);
  const ySpan = Math.abs(maxY - minY);
  const zSpan = Math.abs(maxZ - minZ);
  const scale = 6.7 / Math.max(1, xSpan, ySpan, zSpan);

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
  const zSpan = Math.abs(maxZ - minZ);
  const lateralPad = 1.12;
  const verticalPad = 0.24;

  return {
    minX: xSpan < 0.05 ? -lateralPad : minX - 0.45,
    maxX: xSpan < 0.05 ? lateralPad : maxX + 0.45,
    minY: minY - verticalPad,
    maxY: maxY + verticalPad,
    minZ: zSpan < 0.05 ? -lateralPad : minZ - 0.45,
    maxZ: zSpan < 0.05 ? lateralPad : maxZ + 0.45,
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
  const size = 0.26;
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
    context.font = '800 34px Inter, Arial, sans-serif';
    context.textBaseline = 'middle';
    context.textAlign = 'center';

    if (options?.background) {
      context.fillStyle = options.background;
      const x = 34;
      const y = 42;
      const width = 572;
      const height = 76;
      const radius = 22;
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

    context.shadowColor = 'rgba(111, 211, 255, 0.82)';
    context.shadowBlur = 14;
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
  const scale = options?.scale ?? 0.38;
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


function cameraSettingsFor(preset: WbvViewPreset): {
  position: [number, number, number];
  up: [number, number, number];
  viewHeight: number;
} {
  switch (preset) {
    case 'top':
      return {
        position: [0, 10, 0.01],
        up: [0, 0, -1],
        viewHeight: 4.9,
      };
    case 'side':
      return {
        position: [10, 0.35, 0.01],
        up: [0, 1, 0],
        viewHeight: 7.4,
      };
    case 'fit':
      return {
        position: [4.6, 3.1, 8.2],
        up: [0, 1, 0],
        viewHeight: 7.6,
      };
    case 'reset':
    default:
      return {
        position: [5.2, 3.8, 9.2],
        up: [0, 1, 0],
        viewHeight: 8.2,
      };
  }
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
}: WbvTrajectoryRendererProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [status, setStatus] = useState<RendererStatus>('idle');

  const scenePoints = useMemo(() => scenePointsFromBackend(renderPoints), [renderPoints]);
  const depthTicks = useMemo(() => representativeTicks(renderPoints), [renderPoints]);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;

    if (!host || !canvas) return undefined;

    if (scenePoints.length < 2) {
      setStatus(scenePoints.length === 0 ? 'empty' : 'error');
      return undefined;
    }

    let renderer: THREE.WebGLRenderer | null = null;
    let animationFrame: number | null = null;
    let resizeObserver: ResizeObserver | null = null;

    try {
      const normalizedPoints = createNormalizedPoints(scenePoints);
      const box = sceneBoxFor(normalizedPoints);
      const scene = new THREE.Scene();
      const group = new THREE.Group();
      scene.add(group);

      const camera = new THREE.OrthographicCamera(-5, 5, 5, -5, 0.1, 1000);
      const cameraSettings = cameraSettingsFor(viewPreset);
      camera.position.set(...cameraSettings.position);
      camera.up.set(...cameraSettings.up);
      camera.lookAt(0, 0, 0);

      renderer = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance',
      });
      renderer.setClearColor(0x000000, 0);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

      const boxMaterial = new THREE.LineBasicMaterial({
        color: 0x6fd3ff,
        transparent: true,
        opacity: 0.48,
      });
      group.add(createBoxEdges(box, boxMaterial));

      const planeMaterial = new THREE.LineBasicMaterial({
        color: 0x4ca6cc,
        transparent: true,
        opacity: 0.16,
      });
      const tickMaterial = new THREE.LineBasicMaterial({
        color: 0xc6f6ff,
        transparent: true,
        opacity: 0.52,
      });

      depthTicks.forEach((tick) => {
        const y = box.maxY - (box.maxY - box.minY) * tick.ratio;
        group.add(createDepthPlane(box, y, planeMaterial));
        group.add(createCrossTick(y, tickMaterial));

        const label = createTextSprite(`MD ${tick.label}`, {
          color: '#c6f6ff',
          background: 'rgba(3, 8, 12, 0.64)',
          scale: 0.18,
        });
        label.position.set(box.minX - 0.86, y, box.maxZ + 0.2);
        group.add(label);
      });

      const curve = new THREE.CatmullRomCurve3(normalizedPoints, false, 'catmullrom', 0.04);
      const tubeGeometry = new THREE.TubeGeometry(
        curve,
        Math.max(32, Math.min(220, normalizedPoints.length * 3)),
        0.024,
        10,
        false,
      );
      const tubeMaterial = new THREE.MeshBasicMaterial({
        color: 0x67d599,
        transparent: true,
        opacity: 1,
      });
      group.add(new THREE.Mesh(tubeGeometry, tubeMaterial));

      const glowGeometry = new THREE.TubeGeometry(
        curve,
        Math.max(32, Math.min(220, normalizedPoints.length * 2)),
        0.055,
        10,
        false,
      );
      const glowMaterial = new THREE.MeshBasicMaterial({
        color: 0x67d599,
        transparent: true,
        opacity: 0.12,
      });
      group.add(new THREE.Mesh(glowGeometry, glowMaterial));

      const lineGeometry = new THREE.BufferGeometry().setFromPoints(normalizedPoints);
      const lineMaterial = new THREE.LineBasicMaterial({
        color: 0xe7fbff,
        transparent: true,
        opacity: 0.82,
      });
      group.add(new THREE.Line(lineGeometry, lineMaterial));

      const topMarker = new THREE.Mesh(
        new THREE.SphereGeometry(0.055, 20, 20),
        new THREE.MeshBasicMaterial({ color: 0xc6f6ff }),
      );
      topMarker.position.copy(normalizedPoints[0]);
      group.add(topMarker);

      const baseMarker = new THREE.Mesh(
        new THREE.SphereGeometry(0.055, 20, 20),
        new THREE.MeshBasicMaterial({ color: 0x67d599 }),
      );
      baseMarker.position.copy(normalizedPoints[normalizedPoints.length - 1]);
      group.add(baseMarker);

      const topLabel = createTextSprite(`Top ${formatDepth(renderPoints[0]?.md ?? renderPoints[0]?.tvd, depthUnit)}`, {
        color: '#e7fbff',
        background: 'rgba(3, 8, 12, 0.68)',
        scale: 0.2,
      });
      topLabel.position.set(box.maxX + 0.72, normalizedPoints[0].y, box.maxZ + 0.24);
      group.add(topLabel);

      const baseLabel = createTextSprite(`Base ${formatDepth(renderPoints[renderPoints.length - 1]?.md ?? renderPoints[renderPoints.length - 1]?.tvd, depthUnit)}`, {
        color: '#dff8ec',
        background: 'rgba(3, 8, 12, 0.68)',
        scale: 0.2,
      });
      baseLabel.position.set(box.maxX + 0.78, normalizedPoints[normalizedPoints.length - 1].y, box.maxZ + 0.24);
      group.add(baseLabel);

      const xLabel = createTextSprite('X / EAST', { color: '#80dcff', scale: 0.2 });
      xLabel.position.set(box.maxX + 0.52, box.minY, box.maxZ + 0.2);
      group.add(xLabel);

      const yLabel = createTextSprite('Y / NORTH', { color: '#80dcff', scale: 0.2 });
      yLabel.position.set(box.minX - 0.52, box.minY, box.maxZ + 0.2);
      group.add(yLabel);

      const zLabel = createTextSprite('Z / TVD', { color: '#80dcff', scale: 0.21 });
      zLabel.position.set(box.maxX + 0.56, box.maxY, box.minZ - 0.2);
      group.add(zLabel);

      const renderScene = () => {
        if (!renderer) return;
        renderer.render(scene, camera);
        animationFrame = window.requestAnimationFrame(renderScene);
      };

      const resizeAndRender = () => {
        if (!renderer) return;
        const width = Math.max(1, host.clientWidth);
        const height = Math.max(1, host.clientHeight);
        const aspect = width / height;
        const viewHeight = cameraSettings.viewHeight;
        camera.left = -viewHeight * aspect * 0.5;
        camera.right = viewHeight * aspect * 0.5;
        camera.top = viewHeight * 0.5;
        camera.bottom = -viewHeight * 0.5;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height, false);
      };

      resizeObserver = new ResizeObserver(resizeAndRender);
      resizeObserver.observe(host);
      resizeAndRender();
      renderScene();
      setStatus('rendered');

      return () => {
        if (animationFrame !== null) {
          window.cancelAnimationFrame(animationFrame);
        }
        resizeObserver?.disconnect();
        disposeObject(scene);
        renderer?.dispose();
      };
    } catch (error) {
      console.error('WBV trajectory renderer failed', error);
      setStatus('error');
      renderer?.dispose();
      return undefined;
    }
  }, [depthTicks, depthUnit, renderPoints, scenePoints, viewPreset]);

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
