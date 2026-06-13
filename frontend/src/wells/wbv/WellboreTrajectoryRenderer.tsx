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

function scenePointsFromBackend(points: WbvTrajectoryRenderPoint[]): ScenePoint[] {
  return points.map((point) => {
    const east = finiteNumber(point.x ?? point.east_departure, 0);
    const north = finiteNumber(point.y ?? point.north_departure, 0);
    const verticalDepth = finiteNumber(point.z ?? point.tvd ?? point.md, 0);

    return {
      x: east,
      y: -verticalDepth,
      z: north,
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
    rangeSpan(boundingBox?.z) ??
    rangeSpan(boundingBox?.tvd) ??
    rangeSpan(boundingBox?.md);

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

function disposeObject(object: THREE.Object3D): void {
  object.traverse((child: THREE.Object3D) => {
    const materialHolder = child as THREE.Object3D & { material?: THREE.Material | THREE.Material[] };
    const geometryHolder = child as THREE.Object3D & { geometry?: THREE.BufferGeometry };

    geometryHolder.geometry?.dispose();

    if (Array.isArray(materialHolder.material)) {
      materialHolder.material.forEach((material: THREE.Material) => material.dispose());
    } else {
      materialHolder.material?.dispose();
    }
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

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 1000);
      camera.position.set(7.5, 4.8, 9.2);
      camera.lookAt(0, 0, 0);

      renderer = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance',
      });
      renderer.setClearColor(0x000000, 0);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

      const lineGeometry = new THREE.BufferGeometry().setFromPoints(normalizedPoints);
      const lineMaterial = new THREE.LineBasicMaterial({
        color: 0x67d599,
        linewidth: 1,
      });
      const trajectoryLine = new THREE.Line(lineGeometry, lineMaterial);
      scene.add(trajectoryLine);

      const topMaterial = new THREE.MeshBasicMaterial({ color: 0xa8e9ff });
      const baseMaterial = new THREE.MeshBasicMaterial({ color: 0x67d599 });

      const topMarker = new THREE.Mesh(new THREE.SphereGeometry(0.085, 18, 18), topMaterial);
      topMarker.position.copy(normalizedPoints[0]);
      scene.add(topMarker);

      const baseMarker = new THREE.Mesh(new THREE.SphereGeometry(0.085, 18, 18), baseMaterial);
      baseMarker.position.copy(normalizedPoints[normalizedPoints.length - 1]);
      scene.add(baseMarker);

      const resizeAndRender = () => {
        if (!host || !renderer) return;
        const width = Math.max(1, host.clientWidth);
        const height = Math.max(1, host.clientHeight);
        camera.aspect = width / height;
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
  }, [boundingBox, scenePoints]);

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
        <span>{pointCount} backend render points · {depthUnit}</span>
      </div>
    </div>
  );
}
