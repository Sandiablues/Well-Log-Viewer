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

type WbvTrajectoryRendererProps = {
  renderPoints: WbvTrajectoryRenderPoint[];
  boundingBox?: WbvBoundingBox;
  depthUnit: string;
  viewerState: string;
};

type ScenePoint = {
  x: number;
  y: number;
  z: number;
  md?: number | null;
  tvd?: number | null;
};

type SceneExtent = {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  minZ: number;
  maxZ: number;
  maxSpan: number;
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

function rangeSpan(range: WbvAxisRange | undefined): number | null {
  const min = range?.min;
  const max = range?.max;
  if (typeof min !== 'number' || typeof max !== 'number') return null;
  if (!Number.isFinite(min) || !Number.isFinite(max)) return null;
  return Math.abs(max - min);
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
    const depth = firstFinite(point.tvd, point.md, point.z !== undefined && point.z !== null ? Math.abs(point.z) : null) ?? 0;

    return {
      x: east,
      y: -depth,
      z: north,
      md: point.md,
      tvd: point.tvd,
    };
  });
}

function extentFor(points: ScenePoint[], boundingBox: WbvBoundingBox | undefined): SceneExtent {
  const pointMinX = Math.min(...points.map((point) => point.x));
  const pointMaxX = Math.max(...points.map((point) => point.x));
  const pointMinY = Math.min(...points.map((point) => point.y));
  const pointMaxY = Math.max(...points.map((point) => point.y));
  const pointMinZ = Math.min(...points.map((point) => point.z));
  const pointMaxZ = Math.max(...points.map((point) => point.z));

  const backendVerticalSpan =
    rangeSpan(boundingBox?.tvd) ??
    rangeSpan(boundingBox?.md) ??
    rangeSpan(boundingBox?.z);

  const spans = [
    Math.abs(pointMaxX - pointMinX),
    Math.abs(pointMaxY - pointMinY),
    Math.abs(pointMaxZ - pointMinZ),
    finiteNumber(backendVerticalSpan, 0),
  ];

  return {
    minX: pointMinX,
    maxX: pointMaxX,
    minY: pointMinY,
    maxY: pointMaxY,
    minZ: pointMinZ,
    maxZ: pointMaxZ,
    maxSpan: Math.max(1, ...spans),
  };
}

function normalizeScenePoints(points: ScenePoint[], extent: SceneExtent): THREE.Vector3[] {
  const centerX = (extent.minX + extent.maxX) / 2;
  const centerY = (extent.minY + extent.maxY) / 2;
  const centerZ = (extent.minZ + extent.maxZ) / 2;
  const scale = 7 / extent.maxSpan;

  return points.map((point) => new THREE.Vector3(
    (point.x - centerX) * scale,
    (point.y - centerY) * scale,
    (point.z - centerZ) * scale,
  ));
}

function normalizedSceneBox(points: THREE.Vector3[]): SceneBox {
  const minX = Math.min(...points.map((point) => point.x));
  const maxX = Math.max(...points.map((point) => point.x));
  const minY = Math.min(...points.map((point) => point.y));
  const maxY = Math.max(...points.map((point) => point.y));
  const minZ = Math.min(...points.map((point) => point.z));
  const maxZ = Math.max(...points.map((point) => point.z));

  const xSpan = Math.abs(maxX - minX);
  const ySpan = Math.abs(maxY - minY);
  const zSpan = Math.abs(maxZ - minZ);
  const lateralPad = Math.max(0.95, Math.min(1.75, Math.max(ySpan, 1) * 0.2));
  const verticalPad = Math.max(0.22, Math.min(0.45, Math.max(ySpan, 1) * 0.045));

  return {
    minX: xSpan < 0.05 ? -lateralPad : minX - lateralPad * 0.35,
    maxX: xSpan < 0.05 ? lateralPad : maxX + lateralPad * 0.35,
    minY: minY - verticalPad,
    maxY: maxY + verticalPad,
    minZ: zSpan < 0.05 ? -lateralPad : minZ - lateralPad * 0.35,
    maxZ: zSpan < 0.05 ? lateralPad : maxZ + lateralPad * 0.35,
  };
}

function createBoxEdges(box: SceneBox, material: THREE.LineBasicMaterial): THREE.LineSegments {
  const corners = {
    lbf: new THREE.Vector3(box.minX, box.minY, box.maxZ),
    rbf: new THREE.Vector3(box.maxX, box.minY, box.maxZ),
    rbb: new THREE.Vector3(box.maxX, box.minY, box.minZ),
    lbb: new THREE.Vector3(box.minX, box.minY, box.minZ),
    ltf: new THREE.Vector3(box.minX, box.maxY, box.maxZ),
    rtf: new THREE.Vector3(box.maxX, box.maxY, box.maxZ),
    rtb: new THREE.Vector3(box.maxX, box.maxY, box.minZ),
    ltb: new THREE.Vector3(box.minX, box.maxY, box.minZ),
  };

  const edgePoints = [
    corners.lbf, corners.rbf, corners.rbf, corners.rbb, corners.rbb, corners.lbb, corners.lbb, corners.lbf,
    corners.ltf, corners.rtf, corners.rtf, corners.rtb, corners.rtb, corners.ltb, corners.ltb, corners.ltf,
    corners.lbf, corners.ltf, corners.rbf, corners.rtf, corners.rbb, corners.rtb, corners.lbb, corners.ltb,
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

function createTextSprite(text: string, options?: { color?: string; background?: string; scale?: number }): THREE.Sprite {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 128;
  const context = canvas.getContext('2d');
  if (context) {
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.font = '700 30px Inter, Arial, sans-serif';
    context.textBaseline = 'middle';
    context.textAlign = 'center';
    if (options?.background) {
      context.fillStyle = options.background;
      const x = 28;
      const y = 34;
      const width = 456;
      const height = 60;
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
    context.shadowColor = 'rgba(111, 211, 255, 0.65)';
    context.shadowBlur = 12;
    context.fillStyle = options?.color ?? '#9ee8ff';
    context.fillText(text, canvas.width / 2, canvas.height / 2);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
    depthWrite: false,
  });
  const sprite = new THREE.Sprite(material);
  const scale = options?.scale ?? 0.58;
  sprite.scale.set(scale * 4, scale, 1);
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
    Math.floor(points.length * 0.25),
    Math.floor(points.length * 0.5),
    Math.floor(points.length * 0.75),
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
  boundingBox,
  depthUnit,
  viewerState,
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
      const extent = extentFor(scenePoints, boundingBox);
      const normalizedPoints = normalizeScenePoints(scenePoints, extent);
      const box = normalizedSceneBox(normalizedPoints);

      const scene = new THREE.Scene();
      const camera = new THREE.OrthographicCamera(-5, 5, 5, -5, 0.1, 1000);
      camera.position.set(5.4, 4.2, 8.4);
      camera.up.set(0, 1, 0);
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
        color: 0x5bc7ee,
        transparent: true,
        opacity: 0.58,
      });
      scene.add(createBoxEdges(box, boxMaterial));

      const planeMaterial = new THREE.LineBasicMaterial({
        color: 0x2f7898,
        transparent: true,
        opacity: 0.26,
      });
      depthTicks.forEach((tick) => {
        const y = box.maxY - (box.maxY - box.minY) * tick.ratio;
        scene.add(createDepthPlane(box, y, planeMaterial));
      });

      const tickMaterial = new THREE.LineBasicMaterial({
        color: 0x9ee8ff,
        transparent: true,
        opacity: 0.55,
      });
      depthTicks.forEach((tick) => {
        const y = box.maxY - (box.maxY - box.minY) * tick.ratio;
        const tickGeometry = new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(-0.18, y, 0),
          new THREE.Vector3(0.18, y, 0),
        ]);
        scene.add(new THREE.Line(tickGeometry, tickMaterial));

        const label = createTextSprite(`MD ${tick.label}`, {
          color: '#b9f3ff',
          background: 'rgba(3, 8, 12, 0.54)',
          scale: 0.28,
        });
        label.position.set(box.minX - 0.52, y, box.maxZ + 0.08);
        scene.add(label);
      });

      const trajectoryCurve = new THREE.CatmullRomCurve3(normalizedPoints, false, 'catmullrom', 0.08);
      const tubeGeometry = new THREE.TubeGeometry(
        trajectoryCurve,
        Math.max(24, Math.min(240, normalizedPoints.length * 2)),
        0.018,
        8,
        false,
      );
      const tubeMaterial = new THREE.MeshBasicMaterial({
        color: 0x67d599,
        transparent: true,
        opacity: 0.9,
      });
      scene.add(new THREE.Mesh(tubeGeometry, tubeMaterial));

      const lineGeometry = new THREE.BufferGeometry().setFromPoints(normalizedPoints);
      const lineMaterial = new THREE.LineBasicMaterial({
        color: 0xb9f3ff,
        transparent: true,
        opacity: 0.72,
      });
      scene.add(new THREE.Line(lineGeometry, lineMaterial));

      const topMaterial = new THREE.MeshBasicMaterial({ color: 0xb9f3ff });
      const baseMaterial = new THREE.MeshBasicMaterial({ color: 0x67d599 });

      const topMarker = new THREE.Mesh(new THREE.SphereGeometry(0.045, 18, 18), topMaterial);
      topMarker.position.copy(normalizedPoints[0]);
      scene.add(topMarker);

      const baseMarker = new THREE.Mesh(new THREE.SphereGeometry(0.045, 18, 18), baseMaterial);
      baseMarker.position.copy(normalizedPoints[normalizedPoints.length - 1]);
      scene.add(baseMarker);

      const topLabel = createTextSprite(`Top ${formatDepth(renderPoints[0]?.md ?? renderPoints[0]?.tvd, depthUnit)}`, {
        color: '#dff8ec',
        background: 'rgba(3, 8, 12, 0.58)',
        scale: 0.32,
      });
      topLabel.position.set(0.78, normalizedPoints[0].y, 0.18);
      scene.add(topLabel);

      const baseLabel = createTextSprite(`Base ${formatDepth(renderPoints[renderPoints.length - 1]?.md ?? renderPoints[renderPoints.length - 1]?.tvd, depthUnit)}`, {
        color: '#dff8ec',
        background: 'rgba(3, 8, 12, 0.58)',
        scale: 0.32,
      });
      baseLabel.position.set(0.88, normalizedPoints[normalizedPoints.length - 1].y, 0.18);
      scene.add(baseLabel);

      const xLabel = createTextSprite('X / East', { color: '#80dcff', scale: 0.34 });
      xLabel.position.set(box.maxX + 0.32, box.minY, box.maxZ + 0.12);
      scene.add(xLabel);

      const yLabel = createTextSprite('Y / North', { color: '#80dcff', scale: 0.34 });
      yLabel.position.set(box.minX - 0.32, box.minY, box.maxZ + 0.12);
      scene.add(yLabel);

      const zLabel = createTextSprite('Z / TVD', { color: '#80dcff', scale: 0.36 });
      zLabel.position.set(box.maxX + 0.28, box.maxY, box.minZ - 0.18);
      scene.add(zLabel);

      const resizeAndRender = () => {
        if (!host || !renderer) return;
        const width = Math.max(1, host.clientWidth);
        const height = Math.max(1, host.clientHeight);
        const aspect = width / height;
        const viewHeight = 8.9;
        camera.left = aspect >= 1 ? -viewHeight * aspect * 0.5 : -viewHeight * 0.5;
        camera.right = aspect >= 1 ? viewHeight * aspect * 0.5 : viewHeight * 0.5;
        camera.top = aspect >= 1 ? viewHeight * 0.5 : viewHeight / aspect * 0.5;
        camera.bottom = aspect >= 1 ? -viewHeight * 0.5 : -viewHeight / aspect * 0.5;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height, false);
        renderer.render(scene, camera);
      };

      resizeObserver = new ResizeObserver(() => {
        if (animationFrame !== null) {
          window.cancelAnimationFrame(animationFrame);
        }
        animationFrame = window.requestAnimationFrame(resizeAndRender);
      });
      resizeObserver.observe(host);

      resizeAndRender();
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
  }, [boundingBox, depthTicks, depthUnit, renderPoints, scenePoints]);

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
        <strong>{status === 'rendered' ? '3D trajectory rendered' : '3D trajectory renderer'}</strong>
        <span>{pointCount} backend render points · {depthUnit} · backend-owned package</span>
      </div>
    </div>
  );
}
