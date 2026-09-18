import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera, Grid, Text } from '@react-three/drei';
import * as THREE from 'three';
import { clearBackendSliceCache, fetchSlice, getBackendSliceCacheInfo, getZarrMetadata } from '../services/zarrService';
import VolumePagedRenderer from './VolumePagedRenderer';
import { formatAxisLabel, getCrosslineAxis, getInlineAxis, getVerticalAxis } from '../utils/axisInfo';
import {
  ACTIVE_3D_AXIS_MAPPING,
  buildActive3DSliceWindowCacheKey,
  buildWholeSliceSourceBoundsForAxis,
  formatActive3DSourceBounds,
  getActive3DSliceIndex,
  type Active3DSliceWindowRequest,
} from '../rendering3d/activeSliceRequestModel';


type SceneOpacityGridProps = React.ComponentProps<typeof Grid> & {
  overlayOpacity: number;
};

const SceneOpacityGrid: React.FC<SceneOpacityGridProps> = ({ overlayOpacity, ...props }) => {
  const gridRef = useRef<THREE.Mesh>(null);

  useEffect(() => {
    const material = gridRef.current?.material as THREE.ShaderMaterial | undefined;
    if (!material) return;

    const uniformName = 'uSceneOverlayOpacity';

    if (!material.uniforms[uniformName]) {
      material.uniforms[uniformName] = { value: overlayOpacity };

      if (!material.fragmentShader.includes(`uniform float ${uniformName};`)) {
        material.fragmentShader = material.fragmentShader.replace(
          'uniform float fadeStrength;',
          `uniform float fadeStrength;\nuniform float ${uniformName};`,
        );

        material.fragmentShader = material.fragmentShader.replace(
          'gl_FragColor.a = mix(0.75 * gl_FragColor.a, gl_FragColor.a, g2);',
          `gl_FragColor.a = mix(0.75 * gl_FragColor.a, gl_FragColor.a, g2) * ${uniformName};`,
        );

        material.needsUpdate = true;
      }
    }

    material.uniforms[uniformName].value = overlayOpacity;
  }, [overlayOpacity]);

  return <Grid ref={gridRef} {...props} />;
};

interface WorldSize {
  x: number; // inline
  y: number; // time/depth/sample
  z: number; // crossline
}

interface SavedSceneView {
  cameraPosition: [number, number, number];
  cameraTarget: [number, number, number];
  sceneOffsetX: number;
  sceneOffsetY: number;
}


type SliceAxis = 'inline' | 'crossline' | 'time';
type ColorMapName =
  | 'seismicTrace'
  | 'seismicTraceReverse'
  | 'grayscale'
  | 'blackWhiteBlack'
  | 'redBlackBlue'
  | 'brownWhiteBlue'
  | 'coolwarm';

type WaveDisplayMode = 'full' | 'peaks' | 'troughs';
type TimeRefreshMode = 'immediate' | 'debounced' | 'onRelease';


type CachedSlice = {
  data: Float32Array;
  shape: number[];
};

let sliceCacheLimit = 32;

function trimSliceCache() {
  while (sliceCache.size > sliceCacheLimit) {
    const oldestKey = sliceCache.keys().next().value;
    if (!oldestKey) break;
    sliceCache.delete(oldestKey);
  }
}

function setSliceCacheLimit(nextLimit: number) {
  sliceCacheLimit = Math.max(1, nextLimit);
  trimSliceCache();
}


const indexInputStyle: React.CSSProperties = {
  width: 60,
  textAlign: 'right',
};

const sliceCache = new Map<string, Promise<CachedSlice>>();

function makeSliceCacheKey(zarrPath: string, dim: number, index: number): string {
  return `${zarrPath}|dim=${dim}|index=${index}`;
}

function touchSliceCacheKey(key: string, value: Promise<CachedSlice>) {
  if (sliceCache.has(key)) sliceCache.delete(key);
  sliceCache.set(key, value);

  trimSliceCache();
}

async function fetchSliceCached(zarrPath: string, dim: number, index: number): Promise<CachedSlice> {
  const key = makeSliceCacheKey(zarrPath, dim, index);
  const cached = sliceCache.get(key);
  if (cached) {
    touchSliceCacheKey(key, cached);
    return cached;
  }

  const request = fetchSlice(zarrPath, dim, index).then((slice: any) => ({
    data: slice.data as Float32Array,
    shape: slice.shape as number[],
  }));

  touchSliceCacheKey(key, request);

  try {
    return await request;
  } catch (err) {
    sliceCache.delete(key);
    throw err;
  }
}

function prefetchAdjacentSlices(zarrPath: string, dim: number, index: number, maxIndex: number, axis: SliceAxis) {
  // Time/depth slices are expensive with the current chunk layout, so avoid speculative
  // prefetching there. Inline/crossline benefit from adjacent-slice cache during scrolling.
  if (axis === 'time') return;

  for (const nextIndex of [index - 1, index + 1]) {
    if (nextIndex < 0 || nextIndex > maxIndex) continue;
    fetchSliceCached(zarrPath, dim, nextIndex).catch(() => {
      // Silent prefetch failure. The foreground request will report real errors.
    });
  }
}

type SliceTextureStats = {
  sourceWidth: number;
  sourceHeight: number;
  textureWidth: number;
  textureHeight: number;
  textureScale: number;
  texturePixels: number;
  sourcePixels: number;
  renderMs: number;
  updatedAt: number;
};

interface SlicePlaneProps {
  zarrPath: string;
  dim: number;
  index: number;
  maxIndex: number;
  axis: SliceAxis;
  position: [number, number, number];
  rotation: [number, number, number];
  planeSize: [number, number];
  colorMap: ColorMapName;
  textureScale: number;
  reloadNonce: number;
  amplitudeGain: number;
  clipPercentile: number;
  waveDisplayMode: WaveDisplayMode;
  onLoadState?: (axis: SliceAxis, loading: boolean) => void;
  onTextureStats?: (axis: SliceAxis, stats: SliceTextureStats) => void;
  onPlaneDrag?: (axis: SliceAxis, nextIndex: number) => void;
  onPlaneDragState?: (dragging: boolean, axis: SliceAxis) => void;
  dragCount: number;
  dragWorldSize: number;
  dragAxisVector: [number, number, number];
  flipAxis0?: boolean;
  flipAxis1?: boolean;
}


function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(handle);
  }, [value, delayMs]);

  return debounced;
}

function indexToWorld(index: number, count: number, size: number): number {
  if (count <= 1) return 0;
  return -size / 2 + (index / (count - 1)) * size;
}

function clampIndex(value: number, maxIndex: number): number {
  return Math.max(0, Math.min(maxIndex, value));
}

function worldToIndex(world: number, count: number, size: number): number {
  if (count <= 1 || size === 0) return 0;
  const normalized = (world + size / 2) / size;
  return clampIndex(Math.round(normalized * (count - 1)), count - 1);
}

const SlicePlane: React.FC<SlicePlaneProps> = ({
  zarrPath,
  dim,
  index,
  maxIndex,
  axis,
  position,
  rotation,
  planeSize,
  colorMap,
  textureScale,
  reloadNonce,
  amplitudeGain,
  clipPercentile,
  waveDisplayMode,
  onLoadState,
  onTextureStats,
  onPlaneDrag,
  onPlaneDragState,
  dragCount,
  dragWorldSize,
  dragAxisVector,
  flipAxis0 = false,
  flipAxis1 = false,
}) => {
  const [texture, setTexture] = useState<THREE.DataTexture | null>(null);
  const [sliceData, setSliceData] = useState<CachedSlice | null>(null);
  const requestIdRef = useRef(0);
  const { camera } = useThree();
  const dragRef = useRef<null | {
    pointerId: number;
    startPoint: THREE.Vector3;
    dragPlane: THREE.Plane;
    dragAxis: THREE.Vector3;
    startWorld: number;
  }>(null);

  useEffect(() => {
    let cancelled = false;
    const requestId = ++requestIdRef.current;

    onLoadState?.(axis, true);

    async function loadSliceData() {
      try {
        const slice = await fetchSliceCached(zarrPath, dim, index);
        if (cancelled || requestId !== requestIdRef.current) return;

        setSliceData(slice);
        prefetchAdjacentSlices(zarrPath, dim, index, maxIndex, axis);
      } catch (e) {
        console.error(`Failed to load ${axis} slice`, e);
      } finally {
        if (!cancelled && requestId === requestIdRef.current) onLoadState?.(axis, false);
      }
    }

    loadSliceData();

    return () => {
      cancelled = true;
      onLoadState?.(axis, false);
    };
  }, [zarrPath, dim, index, maxIndex, axis, reloadNonce]);

  useEffect(() => {
    if (!sliceData) return;

    const textureRenderStartedAt = typeof performance !== 'undefined' ? performance.now() : Date.now();
    const data = sliceData.data;

    // Zarrita returns a 2D slice in row-major order with shape [axis0, axis1].
    // For the 3D viewer, axis0 must map to the plane's local X/U direction,
    // and axis1 must map to the plane's local Y/V direction.
    // The earlier version treated axis0 as texture height and axis1 as width,
    // which transposed every slice and made amplitudes fail at intersections.
    const [axis0Count, axis1Count] = sliceData.shape;
    const scale = Math.max(1, Math.floor(textureScale));
    const textureWidth = Math.max(1, axis0Count * scale);
    const textureHeight = Math.max(1, axis1Count * scale);

    const rgbaData = new Uint8Array(textureWidth * textureHeight * 4);

    function percentile(values: number[], p: number): number {
      if (values.length === 0) return 1;
      const sorted = values.slice().sort((a, b) => a - b);
      const idx = Math.max(0, Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * p)));
      return sorted[idx];
    }

    function robustAmplitudeClip(values: Float32Array, percentileValue: number): number {
      // The raw seismic values are not normalized to [-1, 1]. Use a robust
      // per-slice percentile clip so weak and strong events are both visible.
      const maxSamples = 50000;
      const stride = Math.max(1, Math.floor(values.length / maxSamples));
      const absValues: number[] = [];

      for (let i = 0; i < values.length; i += stride) {
        const v = values[i];
        if (Number.isFinite(v)) absValues.push(Math.abs(v));
      }

      const p = Math.max(0.5, Math.min(0.9999, percentileValue / 100));
      const clip = percentile(absValues, p);
      return clip > 0 && Number.isFinite(clip) ? clip : 1;
    }

    const amplitudeClip = robustAmplitudeClip(data, clipPercentile);

    function clamp01(v: number): number {
      return Math.max(0, Math.min(1, v));
    }

    function lerp(a: number, b: number, t: number): number {
      return a + (b - a) * t;
    }

    function mixRgb(a: [number, number, number], b: [number, number, number], t: number): [number, number, number] {
      return [
        Math.round(lerp(a[0], b[0], t)),
        Math.round(lerp(a[1], b[1], t)),
        Math.round(lerp(a[2], b[2], t)),
      ];
    }

    function divergingColor(
      norm: number,
      negativeColor: [number, number, number],
      centerColor: [number, number, number],
      positiveColor: [number, number, number],
    ): [number, number, number] {
      if (norm >= 0) {
        return mixRgb(centerColor, positiveColor, clamp01(norm));
      }
      return mixRgb(centerColor, negativeColor, clamp01(-norm));
    }

    function writeColor(pixelIndex: number, val: number) {
      let norm = Math.max(-1, Math.min(1, (val / amplitudeClip) * amplitudeGain));

      // Polarity display filter. This affects display only; raw amplitudes are unchanged.
      // Peaks = positive amplitudes. Troughs = negative amplitudes.
      if (waveDisplayMode === 'peaks' && norm < 0) norm = 0;
      if (waveDisplayMode === 'troughs' && norm > 0) norm = 0;

      let rgb: [number, number, number];

      switch (colorMap) {
        case 'grayscale': {
          // White-centered grayscale: negative = darker, positive = lighter.
          const gray = Math.round(clamp01(0.5 + 0.5 * norm) * 255);
          rgb = [gray, gray, gray];
          break;
        }
        case 'blackWhiteBlack': {
          // Zero-centered monochrome. Zero is white; strong amplitudes trend to black.
          const gray = Math.round((1 - clamp01(Math.abs(norm))) * 255);
          rgb = [gray, gray, gray];
          break;
        }
        case 'seismicTraceReverse': {
          // Polarity-reversed BWR: positive blue, negative red, white center.
          rgb = divergingColor(norm, [255, 0, 0], [255, 255, 255], [0, 0, 255]);
          break;
        }
        case 'redBlackBlue': {
          // Dark-centered diverging map.
          rgb = divergingColor(norm, [0, 90, 255], [0, 0, 0], [255, 60, 60]);
          break;
        }
        case 'brownWhiteBlue': {
          // Softer geoscience-style diverging map.
          rgb = divergingColor(norm, [50, 90, 210], [255, 255, 255], [150, 95, 45]);
          break;
        }
        case 'coolwarm': {
          // Gentle blue-white-red map.
          rgb = divergingColor(norm, [59, 76, 192], [245, 245, 245], [180, 4, 38]);
          break;
        }
        case 'seismicTrace':
        default: {
          // Variable-density seismic trace style: white at zero, red for positive,
          // blue for negative. No labels, axes, or diagnostic bands are drawn.
          rgb = divergingColor(norm, [0, 0, 255], [255, 255, 255], [255, 0, 0]);
          break;
        }
      }

      rgbaData[pixelIndex * 4] = rgb[0];
      rgbaData[pixelIndex * 4 + 1] = rgb[1];
      rgbaData[pixelIndex * 4 + 2] = rgb[2];
      rgbaData[pixelIndex * 4 + 3] = 255;
    }

    function getValue(axis0: number, axis1: number): number {
      const a0 = Math.max(0, Math.min(axis0Count - 1, axis0));
      const a1 = Math.max(0, Math.min(axis1Count - 1, axis1));
      return data[a0 * axis1Count + a1];
    }

    function sampleBilinear(axis0Float: number, axis1Float: number): number {
      const a0 = Math.floor(axis0Float);
      const a1 = Math.floor(axis1Float);
      const b0 = Math.min(axis0Count - 1, a0 + 1);
      const b1 = Math.min(axis1Count - 1, a1 + 1);
      const t0 = axis0Float - a0;
      const t1 = axis1Float - a1;

      const v00 = getValue(a0, a1);
      const v10 = getValue(b0, a1);
      const v01 = getValue(a0, b1);
      const v11 = getValue(b0, b1);

      const v0 = v00 * (1 - t0) + v10 * t0;
      const v1 = v01 * (1 - t0) + v11 * t0;
      return v0 * (1 - t1) + v1 * t1;
    }

    for (let texY = 0; texY < textureHeight; texY++) {
      const axis1 = textureHeight === 1 ? 0 : (texY / (textureHeight - 1)) * (axis1Count - 1);
      for (let texX = 0; texX < textureWidth; texX++) {
        const axis0 = textureWidth === 1 ? 0 : (texX / (textureWidth - 1)) * (axis0Count - 1);
        const sourceAxis0 = flipAxis0 ? (axis0Count - 1) - axis0 : axis0;
        const sourceAxis1 = flipAxis1 ? (axis1Count - 1) - axis1 : axis1;
        const textureIndex = texY * textureWidth + texX;
        writeColor(textureIndex, sampleBilinear(sourceAxis0, sourceAxis1));
      }
    }

    const tex = new THREE.DataTexture(rgbaData, textureWidth, textureHeight, THREE.RGBAFormat);
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.generateMipmaps = false;
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.needsUpdate = true;

    const textureRenderFinishedAt = typeof performance !== 'undefined' ? performance.now() : Date.now();
    onTextureStats?.(axis, {
      sourceWidth: axis0Count,
      sourceHeight: axis1Count,
      textureWidth,
      textureHeight,
      textureScale: scale,
      texturePixels: textureWidth * textureHeight,
      sourcePixels: axis0Count * axis1Count,
      renderMs: Math.max(0, textureRenderFinishedAt - textureRenderStartedAt),
      updatedAt: Date.now(),
    });

    setTexture((oldTexture) => {
      oldTexture?.dispose();
      return tex;
    });
  }, [sliceData, colorMap, textureScale, amplitudeGain, clipPercentile, waveDisplayMode, flipAxis0, flipAxis1, axis, onTextureStats]);

  useEffect(() => {
    return () => {
      texture?.dispose();
    };
  }, [texture]);

  function handlePointerDown(event: any) {
    if (!event.shiftKey) return;

    event.stopPropagation();
    event.target?.setPointerCapture?.(event.pointerId);

    const cameraNormal = new THREE.Vector3();
    camera.getWorldDirection(cameraNormal);

    const startPoint = event.point.clone();
    const dragPlane = new THREE.Plane().setFromNormalAndCoplanarPoint(cameraNormal, startPoint);
    const dragAxis = new THREE.Vector3(...dragAxisVector).normalize();

    dragRef.current = {
      pointerId: event.pointerId,
      startPoint,
      dragPlane,
      dragAxis,
      startWorld: indexToWorld(index, dragCount, dragWorldSize),
    };

    onPlaneDragState?.(true, axis);
  }

  function handlePointerMove(event: any) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    event.stopPropagation();

    const hit = new THREE.Vector3();
    const ok = event.ray.intersectPlane(drag.dragPlane, hit);
    if (!ok) return;

    const deltaWorld = hit.sub(drag.startPoint).dot(drag.dragAxis);
    const nextWorld = drag.startWorld + deltaWorld;
    const nextIndex = worldToIndex(nextWorld, dragCount, dragWorldSize);

    onPlaneDrag?.(axis, nextIndex);
  }

  function handlePointerUp(event: any) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    event.stopPropagation();
    event.target?.releasePointerCapture?.(event.pointerId);
    dragRef.current = null;
    onPlaneDragState?.(false, axis);
  }

  if (!texture) return null;

  return (
    <mesh
      position={position}
      rotation={rotation}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      onPointerLeave={handlePointerUp}
    >
      <planeGeometry args={planeSize} />
      <meshBasicMaterial
        map={texture}
        side={THREE.DoubleSide}
        transparent={false}
        opacity={1}
        depthWrite={true}
        depthTest={true}
        toneMapped={false}
      />
    </mesh>
  );
};

interface VolumeBoundsProps {
  worldSize: WorldSize;
  color: string;
  adaptive: boolean;
  opacityOverride?: number | null;
}

const VolumeBounds: React.FC<VolumeBoundsProps> = ({ worldSize, color, adaptive, opacityOverride = null }) => {
  return (
    <mesh>
      <boxGeometry args={[worldSize.x, worldSize.y, worldSize.z]} />
      <meshBasicMaterial
        color={color}
        wireframe
        transparent
        opacity={opacityOverride ?? (adaptive ? 0.72 : 0.35)}
      />
    </mesh>
  );
};

type AxisTick = {
  value: number;
  fraction: number;
};

function axisHasNumericRange(axis: any): boolean {
  if (!axis) return false;

  const min = Number(axis.min);
  const max = Number(axis.max);

  return Number.isFinite(min) && Number.isFinite(max) && min !== max;
}

function isDiscreteNumberAxis(axis: any): boolean {
  if (!axis) return false;

  const unit = String(axis.unit || '').toLowerCase();
  const key = String(axis.key || '').toLowerCase();
  const label = String(axis.label || '').toLowerCase();

  return (
    unit === 'number' ||
    unit === 'index' ||
    key.includes('inline') ||
    key.includes('crossline') ||
    label.includes('inline') ||
    label.includes('crossline')
  );
}

function makeAxisEndpointTicks(axis: any): AxisTick[] {
  if (!axisHasNumericRange(axis)) return [];

  const min = Number(axis.min);
  const max = Number(axis.max);

  return [
    { value: min, fraction: 0 },
    { value: max, fraction: 1 },
  ];
}

function formatTickValue(value: number, axis?: any): string {
  if (!Number.isFinite(value)) return '—';

  if (isDiscreteNumberAxis(axis)) {
    return String(Math.round(value));
  }

  if (Math.abs(value) >= 1000) {
    return Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
  }

  if (Number.isInteger(value)) {
    return value.toFixed(0);
  }

  return Number(value.toFixed(2)).toString();
}

function formatAxisTitle(axis: any, fallback: string): string {
  if (!axis) return fallback;

  const label = formatAxisLabel(axis);
  const unit = axis.unit;

  if (!unit || unit === 'number' || unit === 'index') {
    return label;
  }

  return `${label} (${unit})`;
}

function AxisTextLabel({
  position,
  rotation,
  children,
  title = false,
  color,
  adaptive,
  sizeScale = 1,
  opacityScale = 1,
}: {
  position: [number, number, number];
  rotation: [number, number, number];
  children: React.ReactNode;
  title?: boolean;
  color: string;
  adaptive: boolean;
  sizeScale?: number;
  opacityScale?: number;
}) {
  return (
    <Text
      position={position}
      rotation={rotation}
      fontSize={(title ? 0.115 : 0.095) * sizeScale}
      color={adaptive ? color : '#f5f7fb'}
      anchorX="center"
      anchorY="middle"
      depthOffset={0}
      renderOrder={0}
    >
      {children}
      <meshBasicMaterial
        attach="material"
        color={adaptive ? color : '#f5f7fb'}
        transparent
        opacity={(adaptive ? 1 : (title ? 0.82 : 0.68)) * opacityScale}
        depthTest={true}
        depthWrite={false}
      />
    </Text>
  );
}

function AxisRulerLabels({
  worldSize,
  volume,
  inlineCount,
  crosslineCount,
  timeCount,
  color,
  adaptive,
  sizeScale = 1,
  opacityScale = 1,
}: {
  worldSize: WorldSize;
  volume?: any;
  inlineCount: number;
  crosslineCount: number;
  timeCount: number;
  color: string;
  adaptive: boolean;
  sizeScale?: number;
  opacityScale?: number;
}) {
  // Bounding-box rulers should match the displayed cube extents.
  // Inline/crossline use rendered array index ranges. Header-derived survey
  // numbers can be added later as an alternate coordinate mode.
  const inlineAxis = {
    key: 'inline',
    label: 'Inline',
    min: 0,
    max: Math.max(0, inlineCount - 1),
    unit: 'index',
  };

  const crosslineAxis = {
    key: 'crossline',
    label: 'Crossline',
    min: 0,
    max: Math.max(0, crosslineCount - 1),
    unit: 'index',
  };

  const metadataVerticalAxis = getVerticalAxis(volume);
  const verticalAxis = metadataVerticalAxis || {
    key: 'vertical',
    label: 'Time/depth',
    min: 0,
    max: Math.max(0, timeCount - 1),
    unit: 'index',
  };

  const maxWorld = Math.max(worldSize.x, worldSize.y, worldSize.z);

  // Small offset: close to the outer box line, not floating out in space.
  const edgeOffset = Math.max(0.06, maxWorld * 0.012);
  const titleOffset = Math.max(0.16, maxWorld * 0.035);

  const inlineTicks = makeAxisEndpointTicks(inlineAxis);
  const crosslineTicks = makeAxisEndpointTicks(crosslineAxis);
  const verticalTicks = makeAxisEndpointTicks(verticalAxis);

  // Text rotations:
  // inline: vertical text plane on the front outside face, reading along X
  // crossline: vertical text plane on the right outside face, reading along Z
  // vertical: vertical text plane on the rear/side outside edge, reading along Y
  //
  // Do not lay inline/crossline labels flat on the floor; that only reads top-down.
  const inlineRotation: [number, number, number] = [0, Math.PI, 0];
  const crosslineRotation: [number, number, number] = [0, Math.PI / 2, 0];
  const verticalRotation: [number, number, number] = [0, 0, Math.PI / 2];

  const yBottom = -worldSize.y / 2;
  const xLeft = -worldSize.x / 2;
  const xRight = worldSize.x / 2;
  const zFront = -worldSize.z / 2;
  const zBack = worldSize.z / 2;

  return (
    <>
      {/* Inline endpoint values, directly outside the front-bottom inline edge */}
      {inlineTicks.map((tick) => (
        <AxisTextLabel
          color={color}
          adaptive={adaptive}
          sizeScale={sizeScale}
          opacityScale={opacityScale}
          key={`inline-${tick.fraction}`}
          rotation={inlineRotation}
          position={[
            xLeft + tick.fraction * worldSize.x,
            yBottom - edgeOffset,
            zFront - edgeOffset,
          ]}
        >
          {formatTickValue(tick.value, inlineAxis)}
        </AxisTextLabel>
      ))}

      {inlineTicks.length > 0 && (
        <AxisTextLabel
          color={color}
          adaptive={adaptive}
          sizeScale={sizeScale}
          opacityScale={opacityScale}
          title
          rotation={inlineRotation}
          position={[0, yBottom - titleOffset, zFront - edgeOffset]}
        >
          {formatAxisTitle(inlineAxis, 'Inline')}
        </AxisTextLabel>
      )}

      {/* Crossline endpoint values, directly outside the right-bottom crossline edge */}
      {crosslineTicks.map((tick) => (
        <AxisTextLabel
          color={color}
          adaptive={adaptive}
          sizeScale={sizeScale}
          opacityScale={opacityScale}
          key={`crossline-${tick.fraction}`}
          rotation={crosslineRotation}
          position={[
            xRight + edgeOffset,
            yBottom - edgeOffset,
            zFront + tick.fraction * worldSize.z,
          ]}
        >
          {formatTickValue(tick.value, crosslineAxis)}
        </AxisTextLabel>
      ))}

      {crosslineTicks.length > 0 && (
        <AxisTextLabel
          color={color}
          adaptive={adaptive}
          sizeScale={sizeScale}
          opacityScale={opacityScale}
          title
          rotation={crosslineRotation}
          position={[xRight + edgeOffset, yBottom - titleOffset, 0]}
        >
          {formatAxisTitle(crosslineAxis, 'Crossline')}
        </AxisTextLabel>
      )}

      {/* Vertical endpoint values, directly outside one rear-left vertical edge */}
      {verticalTicks.map((tick) => (
        <AxisTextLabel
          color={color}
          adaptive={adaptive}
          sizeScale={sizeScale}
          opacityScale={opacityScale}
          key={`vertical-${tick.fraction}`}
          rotation={verticalRotation}
          position={[
            xLeft - edgeOffset,
            worldSize.y / 2 - tick.fraction * worldSize.y,
            zBack + edgeOffset,
          ]}
        >
          {formatTickValue(tick.value, verticalAxis)}
        </AxisTextLabel>
      ))}

      {verticalTicks.length > 0 && (
        <AxisTextLabel
          color={color}
          adaptive={adaptive}
          sizeScale={sizeScale}
          opacityScale={opacityScale}
          title
          rotation={verticalRotation}
          position={[xLeft - titleOffset, 0, zBack + edgeOffset]}
        >
          {formatAxisTitle(verticalAxis, 'Vertical')}
        </AxisTextLabel>
      )}
    </>
  );
}

type SdvCanvasShadeId = 'dark' | 'charcoal' | 'slate' | 'mid' | 'soft' | 'light';

type SceneOverlayAppearance = {
  grid: {
    color: string | null;
    opacity: number;
  };
  bounds: {
    color: string | null;
    opacity: number | null;
  };
  axes: {
    scale: number;
  };
  labels: {
    color: string | null;
    sizeScale: number;
    opacityScale: number;
  };
  compass: {
    sizeScale: number;
    opacity: number;
  };
};

const DEFAULT_SCENE_OVERLAY_APPEARANCE: SceneOverlayAppearance = {
  grid: { color: null, opacity: 1 },
  bounds: { color: null, opacity: null },
  axes: { scale: 1 },
  labels: { color: null, sizeScale: 1, opacityScale: 1 },
  compass: { sizeScale: 1, opacity: 1 },
};

interface Seismic3DViewerProps {
  zarrPath: string;
  volume?: any;
  canvasBackground?: string;
  canvasShadeId?: SdvCanvasShadeId;
  emptyState?: boolean;
  emptyStateMessage?: string;
}

type SdvCanvasEnvironmentPalette = {
  boundingBoxColor: string | null;
  gridColor: string | null;
  groundPlaneColor: string | null;
  rigColor: string;
  neutralTextColor: string;
  axisTextColor: string;
};

/* Copied from the live WBV WellboreTrajectoryRenderer shade resolver. */
function resolveSdvCanvasEnvironmentPalette(
  shadeId: SdvCanvasShadeId,
): SdvCanvasEnvironmentPalette {
  switch (shadeId) {
    case 'charcoal':
      return {
        boundingBoxColor: '#70828B',
        gridColor: '#667983',
        groundPlaneColor: '#303A3F',
        rigColor: '#D8E5E9',
        neutralTextColor: '#E8EFF2',
        axisTextColor: '#B9D5DE',
      };
    case 'slate':
      return {
        boundingBoxColor: '#9AA8AD',
        gridColor: '#88989E',
        groundPlaneColor: '#59666B',
        rigColor: '#ECF3F5',
        neutralTextColor: '#F2F6F7',
        axisTextColor: '#D5E4E8',
      };
    case 'mid':
      return {
        boundingBoxColor: '#46565D',
        gridColor: '#52636A',
        groundPlaneColor: '#768388',
        rigColor: '#303F45',
        neutralTextColor: '#1B282E',
        axisTextColor: '#29434D',
      };
    case 'soft':
      return {
        boundingBoxColor: '#6E7B80',
        gridColor: '#7B888D',
        groundPlaneColor: '#B2BABD',
        rigColor: '#46575D',
        neutralTextColor: '#2A373C',
        axisTextColor: '#3F5962',
      };
    case 'light':
      return {
        boundingBoxColor: '#606C73',
        gridColor: '#7F8B92',
        groundPlaneColor: '#CBD3D8',
        rigColor: '#8A979E',
        neutralTextColor: '#404548',
        axisTextColor: '#414A50',
      };
    case 'dark':
    default:
      return {
        boundingBoxColor: null,
        gridColor: null,
        groundPlaneColor: null,
        rigColor: '#E6FCFF',
        neutralTextColor: '#F4FEFF',
        axisTextColor: '#80DCFF',
      };
  }
}

function isLightCanvasShade(shadeId: SdvCanvasShadeId): boolean {
  return shadeId === 'soft' || shadeId === 'light';
}

type SdvCompassPalette = {
  surface: string;
  border: string;
  text: string;
  north: string;
};

/* Exact WBV compass shade values copied from WBV_CANVAS_SHADE_OPTIONS. */
function resolveSdvCompassPalette(shadeId: SdvCanvasShadeId): SdvCompassPalette {
  switch (shadeId) {
    case 'charcoal':
      return {
        surface: 'rgba(27, 38, 43, 0.90)',
        border: 'rgba(151, 186, 197, 0.48)',
        text: '#dce7ea',
        north: '#a9d6df',
      };
    case 'slate':
      return {
        surface: 'rgba(58, 70, 75, 0.90)',
        border: 'rgba(191, 211, 216, 0.50)',
        text: '#f0f5f6',
        north: '#c9e3e8',
      };
    case 'mid':
      return {
        surface: 'rgba(76, 88, 94, 0.94)',
        border: 'rgba(66, 88, 97, 0.78)',
        text: '#F2F7F8',
        north: '#C6E6EC',
      };
    case 'soft':
      return {
        surface: 'rgba(99, 113, 120, 0.92)',
        border: 'rgba(80, 105, 114, 0.72)',
        text: '#F6FAFB',
        north: '#D1E9EE',
      };
    case 'light':
      return {
        surface: 'rgba(111, 126, 133, 0.94)',
        border: 'rgba(74, 101, 111, 0.74)',
        text: '#F2F8FA',
        north: '#D7F0F4',
      };
    case 'dark':
    default:
      return {
        surface: 'rgba(4, 11, 15, 0.80)',
        border: 'rgba(84, 203, 229, 0.42)',
        text: '#cdebf0',
        north: '#8ff2ff',
      };
  }
}

function SdvCompassCameraSync({
  compassRoseRef,
  compassAngleRef,
}: {
  compassRoseRef: React.RefObject<HTMLDivElement | null>;
  compassAngleRef: React.MutableRefObject<number | null>;
}) {
  const cameraDirectionRef = useRef(new THREE.Vector3());

  useFrame(({ camera }, delta) => {
    const compassRose = compassRoseRef.current;
    if (!compassRose) return;

    const cameraDirection = cameraDirectionRef.current;
    camera.getWorldDirection(cameraDirection);
    const horizontalMagnitude = Math.hypot(cameraDirection.x, cameraDirection.z);

    if (horizontalMagnitude > 0.04) {
      const viewHeadingDeg = Math.atan2(cameraDirection.x, cameraDirection.z) * 180 / Math.PI;
      const rawRoseAngleDeg = -viewHeadingDeg;
      const previousAngle = compassAngleRef.current;
      let continuousAngle = rawRoseAngleDeg;

      if (previousAngle !== null) {
        while (continuousAngle - previousAngle > 180) continuousAngle -= 360;
        while (continuousAngle - previousAngle < -180) continuousAngle += 360;

        const deltaMs = Math.max(delta * 1000, 1);
        const smoothing = 1 - Math.exp(-deltaMs / 90);
        continuousAngle = previousAngle + (continuousAngle - previousAngle) * smoothing;
      }

      compassAngleRef.current = continuousAngle;
      compassRose.style.transform = `rotate(${continuousAngle.toFixed(3)}deg)`;
      compassRose.dataset.edgeOn = 'false';
    } else {
      compassRose.dataset.edgeOn = 'true';
    }
  });

  return null;
}

function resolveAdaptiveAxisLineColors(
  shadeId: SdvCanvasShadeId,
): { x: string; y: string; z: string } {
  if (shadeId === 'light') {
    return {
      x: '#8F1F24',
      y: '#246B3A',
      z: '#1E4F9A',
    };
  }

  return {
    x: '#B23A3A',
    y: '#2F7D4A',
    z: '#2F63B5',
  };
}

function ShadeAwareAxesHelper({
  size,
  shadeId,
}: {
  size: number;
  shadeId: SdvCanvasShadeId;
}) {
  const helper = useMemo(() => {
    const next = new THREE.AxesHelper(size);
    const colors = resolveAdaptiveAxisLineColors(shadeId);
    next.setColors(
      new THREE.Color(colors.x),
      new THREE.Color(colors.y),
      new THREE.Color(colors.z),
    );
    return next;
  }, [size, shadeId]);

  useEffect(() => {
    return () => {
      helper.geometry.dispose();
      if (Array.isArray(helper.material)) {
        helper.material.forEach((material) => material.dispose());
      } else {
        helper.material.dispose();
      }
    };
  }, [helper]);

  return <primitive object={helper} />;
}

export const Seismic3DViewer: React.FC<Seismic3DViewerProps> = ({
  zarrPath,
  volume,
  canvasBackground = '#111',
  canvasShadeId = 'dark',
  emptyState = false,
  emptyStateMessage = 'No volume loaded.',
}) => {
  const [metadata, setMetadata] = useState<any>(() => (
    emptyState ? { shape: [100, 100, 100] } : null
  ));
  const [indices, setIndices] = useState({ inline: 0, crossline: 0, time: 0 });
  const [colorMap, setColorMap] = useState<ColorMapName>('seismicTrace');
  const [textureScale, setTextureScale] = useState(2);
  const [verticalExaggeration, setVerticalExaggeration] = useState(1.5);
  const [amplitudeGain, setAmplitudeGain] = useState(1.0);
  const [clipPercentile, setClipPercentile] = useState(98.5);
  const [waveDisplayMode, setWaveDisplayMode] = useState<WaveDisplayMode>('full');
  const [showGrid, setShowGrid] = useState(true);
  const [showBounds, setShowBounds] = useState(true);
  const [showAxes, setShowAxes] = useState(true);
  const [showAxisLabels, setShowAxisLabels] = useState(true);
  const [showCompass, setShowCompass] = useState(true);
  const [paneDragging, setPaneDragging] = useState(false);
  const [menuCollapsed, setMenuCollapsed] = useState(false);
  const [infoCollapsed, setInfoCollapsed] = useState(false);
  const [activeControlTab, setActiveControlTab] = useState<'view' | 'planes' | 'volume' | 'amplitude' | 'performance'>('view');
  const [fastPreviewWhileMoving, setFastPreviewWhileMoving] = useState(true);
  const [livePreviewWhileDragging, setLivePreviewWhileDragging] = useState(false);
  const [draggingAxis, setDraggingAxis] = useState<SliceAxis | null>(null);
  const [timeRefreshMode, setTimeRefreshMode] = useState<TimeRefreshMode>('debounced');
  const [cacheSize, setCacheSize] = useState(32);
  const [backendCacheInfo, setBackendCacheInfo] = useState<any>(null);
  const [showVolumeInfo, setShowVolumeInfo] = useState(true);
  const [showSliceInfo, setShowSliceInfo] = useState(true);
  const [committedTimeIndex, setCommittedTimeIndex] = useState(0);
  const [sceneOffsetX, setSceneOffsetX] = useState(0);
  const [sceneOffsetY, setSceneOffsetY] = useState(0);
  const [navigationZoomPercent, setNavigationZoomPercent] = useState(100);
  const [navigationOrientation, setNavigationOrientation] = useState<'front' | 'right' | 'left' | 'back' | 'top' | null>(null);
  const [horizontalRotationLocked, setHorizontalRotationLocked] = useState(false);
  const [verticalRotationLocked, setVerticalRotationLocked] = useState(false);
  const horizontalRotationHoldRef = useRef<{ delay: number | null; repeat: number | null; held: boolean }>({ delay: null, repeat: null, held: false });
  const verticalRotationHoldRef = useRef<{ delay: number | null; repeat: number | null; held: boolean }>({ delay: null, repeat: null, held: false });
  const [savedSceneView, setSavedSceneView] = useState<SavedSceneView | null>(null);
  const [sceneOverlaysInfoOpen, setSceneOverlaysInfoOpen] = useState(false);
  const [sceneInfoOpen, setSceneInfoOpen] = useState(false);
  const [sceneOverlaysModalOpen, setSceneOverlaysModalOpen] = useState(false);
  const [selectedSceneOverlayLayer, setSelectedSceneOverlayLayer] = useState<'grid' | 'bounds' | 'axes' | 'labels' | 'compass'>('grid');
  const [sceneOverlayDraftVisibility, setSceneOverlayDraftVisibility] = useState({
    grid: true,
    bounds: true,
    axes: true,
    labels: true,
    compass: true,
  });
  const [sceneOverlayAppearance, setSceneOverlayAppearance] = useState<SceneOverlayAppearance>(
    () => structuredClone(DEFAULT_SCENE_OVERLAY_APPEARANCE),
  );
  const [sceneOverlayDraftAppearance, setSceneOverlayDraftAppearance] = useState<SceneOverlayAppearance>(
    () => structuredClone(DEFAULT_SCENE_OVERLAY_APPEARANCE),
  );
  const sceneOverlaysModalRef = useRef<HTMLElement | null>(null);
  const sceneOverlaysModalDragRef = useRef<{
    pointerId: number;
    startPointerX: number;
    startPointerY: number;
    startOffsetX: number;
    startOffsetY: number;
    startRectLeft: number;
    startRectTop: number;
    modalWidth: number;
    modalHeight: number;
  } | null>(null);
  const [sceneOverlaysModalOffset, setSceneOverlaysModalOffset] = useState({ x: 0, y: 0 });
  const scenePanRef = useRef<null | {
    pointerId: number;
    startX: number;
    startY: number;
    startOffsetX: number;
    startOffsetY: number;
  }>(null);
  const controlsRef = useRef<any>(null);
  const compassRoseRef = useRef<HTMLDivElement | null>(null);
  const compassAngleRef = useRef<number | null>(null);
  const compassPalette = resolveSdvCompassPalette(canvasShadeId);
  const [visiblePlanes, setVisiblePlanes] = useState<Record<SliceAxis, boolean>>({
    inline: !emptyState,
    crossline: false,
    time: false,
  });
  const [loadingPlanes, setLoadingPlanes] = useState<Record<SliceAxis, boolean>>({
    inline: false,
    crossline: false,
    time: false,
  });
  const [textureStats, setTextureStats] = useState<Partial<Record<SliceAxis, SliceTextureStats>>>({});

  const [volumeStackEnabled, setVolumeStackEnabled] = useState(false);
  const [volumeBackgroundMode, setVolumeBackgroundMode] = useState<'off' | 'whole' | 'paged' | 'thickness'>('off');
  const [volumeExtentMode, setVolumeExtentMode] = useState<'full' | 'local'>('full');
  const [volumeQuality, setVolumeQuality] = useState<'preview' | 'balanced' | 'high' | 'diagnostic'>('balanced');
  const [volumeWheelScrollEnabled, setVolumeWheelScrollEnabled] = useState(false);
  const [volumeRenderDim, setVolumeRenderDim] = useState<0 | 1 | 2>(0);
  const [volumeCenterIndex, setVolumeCenterIndex] = useState(0);
  const [directionLoadRequest, setDirectionLoadRequest] = useState(0);
  const [directionPauseRequest, setDirectionPauseRequest] = useState(0);
  const [directionUnloadRequest, setDirectionUnloadRequest] = useState(0);
  const [directionLoadStatus, setDirectionLoadStatus] = useState<any | null>(null);
  const [volumeWindowSize, setVolumeWindowSize] = useState(64);
  const [volumeStep, setVolumeStep] = useState(4);
  const [useStepForPaging, setUseStepForPaging] = useState(false);
  const [volumeOpacity, setVolumeOpacity] = useState(0.35);
  const [volumeDensity, setVolumeDensity] = useState(1.5);
  const [volumeThreshold, setVolumeThreshold] = useState(0);
  const [volumeCacheStatus, setVolumeCacheStatus] = useState<{ loading: boolean; message: string } | null>(null);
  const [planeReloadNonce, setPlaneReloadNonce] = useState<Record<SliceAxis, number>>({
    inline: 0,
    crossline: 0,
    time: 0,
  });

  const openSceneOverlaysModal = useCallback(() => {
    setSceneOverlayDraftVisibility({
      grid: showGrid,
      bounds: showBounds,
      axes: showAxes,
      labels: showAxisLabels,
      compass: showCompass,
    });
    setSceneOverlayDraftAppearance(structuredClone(sceneOverlayAppearance));
    setSceneOverlaysModalOpen(true);
  }, [showGrid, showBounds, showAxes, showAxisLabels, showCompass, sceneOverlayAppearance]);

  const cancelSceneOverlaysModal = useCallback(() => {
    setSceneOverlaysModalOpen(false);
  }, []);

  const applySceneOverlaysModal = useCallback(() => {
    setShowGrid(sceneOverlayDraftVisibility.grid);
    setShowBounds(sceneOverlayDraftVisibility.bounds);
    setShowAxes(sceneOverlayDraftVisibility.axes);
    setShowAxisLabels(sceneOverlayDraftVisibility.labels);
    setShowCompass(sceneOverlayDraftVisibility.compass);
    setSceneOverlayAppearance(structuredClone(sceneOverlayDraftAppearance));
    setSceneOverlaysModalOpen(false);
  }, [sceneOverlayDraftVisibility, sceneOverlayDraftAppearance]);

  const resetSelectedSceneOverlayLayer = useCallback(() => {
    setSceneOverlayDraftVisibility((current) => ({
      ...current,
      [selectedSceneOverlayLayer]: true,
    }));
    setSceneOverlayDraftAppearance((current) => ({
      ...current,
      [selectedSceneOverlayLayer]: structuredClone(DEFAULT_SCENE_OVERLAY_APPEARANCE[selectedSceneOverlayLayer]),
    }));
  }, [selectedSceneOverlayLayer]);

  const beginSceneOverlaysModalDrag = useCallback((event: React.PointerEvent<HTMLElement>) => {
    if (event.button !== 0) return;
    const target = event.target as HTMLElement;
    if (target.closest('button, input, select, textarea, [role="button"]')) return;

    const modal = sceneOverlaysModalRef.current;
    if (!modal) return;

    const rect = modal.getBoundingClientRect();
    sceneOverlaysModalDragRef.current = {
      pointerId: event.pointerId,
      startPointerX: event.clientX,
      startPointerY: event.clientY,
      startOffsetX: sceneOverlaysModalOffset.x,
      startOffsetY: sceneOverlaysModalOffset.y,
      startRectLeft: rect.left,
      startRectTop: rect.top,
      modalWidth: rect.width,
      modalHeight: rect.height,
    };

    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  }, [sceneOverlaysModalOffset]);

  const moveSceneOverlaysModalDrag = useCallback((event: React.PointerEvent<HTMLElement>) => {
    const drag = sceneOverlaysModalDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    if ((event.buttons & 1) !== 1) {
      sceneOverlaysModalDragRef.current = null;
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      return;
    }

    const deltaX = event.clientX - drag.startPointerX;
    const deltaY = event.clientY - drag.startPointerY;

    const unclampedX = drag.startOffsetX + deltaX;
    const unclampedY = drag.startOffsetY + deltaY;

    const minOffsetX = drag.startOffsetX - drag.startRectLeft;
    const minOffsetY = drag.startOffsetY - drag.startRectTop;
    const maxOffsetX = drag.startOffsetX + (window.innerWidth - (drag.startRectLeft + drag.modalWidth));
    const maxOffsetY = drag.startOffsetY + (window.innerHeight - (drag.startRectTop + drag.modalHeight));

    setSceneOverlaysModalOffset({
      x: Math.min(maxOffsetX, Math.max(minOffsetX, unclampedX)),
      y: Math.min(maxOffsetY, Math.max(minOffsetY, unclampedY)),
    });
    event.preventDefault();
  }, []);

  const endSceneOverlaysModalDrag = useCallback((event: React.PointerEvent<HTMLElement>) => {
    const drag = sceneOverlaysModalDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    sceneOverlaysModalDragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const loseSceneOverlaysModalPointerCapture = useCallback(() => {
    sceneOverlaysModalDragRef.current = null;
  }, []);

  const resetCubeControls = useCallback(() => {
    // Reset cube display controls only.
    // Preserve Volume Stack workflow state:
    // - selected direction
    // - loaded direction cache/status
    // - Volume Stack enabled/disabled state
    // - mouse-wheel scroll setting
    setVolumeBackgroundMode('off');
    setVolumeExtentMode('full');
    setVolumeQuality('balanced');
    setVolumeWindowSize(64);
    setVolumeStep(4);
    setVolumeOpacity(0.35);
    setVolumeDensity(1.5);
    setVolumeThreshold(0);
  }, []);

  const canvasEnvironmentPalette = resolveSdvCanvasEnvironmentPalette(canvasShadeId);
  const canvasShadeAdaptive = isLightCanvasShade(canvasShadeId);
  const canvasBoundingBoxColor = canvasShadeAdaptive
    ? (canvasEnvironmentPalette.boundingBoxColor ?? '#587080')
    : '#ffffff';
  const canvasGridColor = canvasEnvironmentPalette.gridColor ?? '#526878';
  const activeSceneOverlayAppearance = sceneOverlaysModalOpen
    ? sceneOverlayDraftAppearance
    : sceneOverlayAppearance;
  const activeSceneOverlayVisibility = sceneOverlaysModalOpen
    ? sceneOverlayDraftVisibility
    : {
        grid: showGrid,
        bounds: showBounds,
        axes: showAxes,
        labels: showAxisLabels,
        compass: showCompass,
      };

  const sceneOverlayGridColor = activeSceneOverlayAppearance.grid.color;
  const sceneOverlayGridOpacity = activeSceneOverlayAppearance.grid.opacity;
  const sceneOverlayBoundingBoxColor = activeSceneOverlayAppearance.bounds.color ?? canvasBoundingBoxColor;
  const sceneOverlayBoundingBoxOpacity = activeSceneOverlayAppearance.bounds.opacity;
  const sceneOverlayAxisScale = activeSceneOverlayAppearance.axes.scale;
  const sceneOverlayLabelColor = activeSceneOverlayAppearance.labels.color ?? canvasEnvironmentPalette.axisTextColor;
  const sceneOverlayLabelSizeScale = activeSceneOverlayAppearance.labels.sizeScale;
  const sceneOverlayLabelOpacityScale = activeSceneOverlayAppearance.labels.opacityScale;
  const sceneOverlayCompassSizeScale = activeSceneOverlayAppearance.compass.sizeScale;
  const sceneOverlayCompassOpacity = activeSceneOverlayAppearance.compass.opacity;

  const [inlineCount, crosslineCount, timeCount] = metadata?.shape ?? [1, 1, 1];

  const debouncedIndices = useDebouncedValue(indices, 250);
  const livePreviewIndices = useDebouncedValue(indices, 100);
  const debouncedAmplitudeGain = useDebouncedValue(amplitudeGain, 150);
  const debouncedClipPercentile = useDebouncedValue(clipPercentile, 150);

  const isSliceMoving =
    indices.inline !== debouncedIndices.inline ||
    indices.crossline !== debouncedIndices.crossline ||
    indices.time !== debouncedIndices.time;

  const isLivePreviewing = livePreviewWhileDragging && paneDragging && draggingAxis !== null;
  const effectiveTextureScale = (fastPreviewWhileMoving && isSliceMoving) || isLivePreviewing ? 1 : textureScale;
  const activeTextureDetailMode = effectiveTextureScale === textureScale
    ? 'settled'
    : isLivePreviewing
      ? 'live preview'
      : 'moving preview';
  const activeTextureStats = textureStats[draggingAxis || 'inline'] || textureStats.inline || textureStats.crossline || textureStats.time || null;

  const activeDiagnosticAxis = useMemo<SliceAxis>(() => {
    if (volumeStackEnabled) {
      if (volumeRenderDim === 0) return 'inline';
      if (volumeRenderDim === 1) return 'crossline';
      return 'time';
    }

    if (draggingAxis) return draggingAxis;
    if (visiblePlanes.inline) return 'inline';
    if (visiblePlanes.crossline) return 'crossline';
    if (visiblePlanes.time) return 'time';
    return 'inline';
  }, [volumeStackEnabled, volumeRenderDim, draggingAxis, visiblePlanes.inline, visiblePlanes.crossline, visiblePlanes.time]);

  const activeDiagnosticSliceIndex = getActive3DSliceIndex(activeDiagnosticAxis, {
    inline: volumeStackEnabled && volumeRenderDim === 0 ? volumeCenterIndex : indices.inline,
    crossline: volumeStackEnabled && volumeRenderDim === 1 ? volumeCenterIndex : indices.crossline,
    time: volumeStackEnabled && volumeRenderDim === 2 ? volumeCenterIndex : indices.time,
  });

  const activeDiagnosticSourceBounds = useMemo(() => buildWholeSliceSourceBoundsForAxis(activeDiagnosticAxis, {
    inlineCount,
    crosslineCount,
    sampleCount: timeCount,
  }), [activeDiagnosticAxis, inlineCount, crosslineCount, timeCount]);

  const activeDiagnosticAxisMapping = ACTIVE_3D_AXIS_MAPPING[activeDiagnosticAxis];

  const activeDiagnosticRequest = useMemo<Active3DSliceWindowRequest>(() => ({
    representationId:
      String(volume?.msi_representation_id || volume?.id || volume?.volume_id || zarrPath),
    axis: activeDiagnosticAxis,
    sliceIndex: activeDiagnosticSliceIndex,
    sourceBounds: activeDiagnosticSourceBounds,
    outputShape: {
      width: Math.max(1, Math.floor(activeTextureStats?.textureWidth || activeTextureStats?.sourceWidth || 1)),
      height: Math.max(1, Math.floor(activeTextureStats?.textureHeight || activeTextureStats?.sourceHeight || 1)),
    },
    clipPercentile,
    gain: amplitudeGain,
    reversePolarity: false,
    colorMode: colorMap === 'grayscale' || colorMap === 'blackWhiteBlack' ? 'grayscale' : 'color',
    quality: effectiveTextureScale >= 2 ? 'high' : 'preview',
  }), [
    volume?.msi_representation_id,
    volume?.id,
    volume?.volume_id,
    zarrPath,
    activeDiagnosticAxis,
    activeDiagnosticSliceIndex,
    activeDiagnosticSourceBounds,
    activeTextureStats?.textureWidth,
    activeTextureStats?.textureHeight,
    activeTextureStats?.sourceWidth,
    activeTextureStats?.sourceHeight,
    clipPercentile,
    amplitudeGain,
    colorMap,
    effectiveTextureScale,
  ]);

  const activeDiagnosticCacheKey = useMemo(() => (
    buildActive3DSliceWindowCacheKey(activeDiagnosticRequest)
  ), [activeDiagnosticRequest]);

  const renderedInlineIndex =
    isLivePreviewing && draggingAxis === 'inline'
      ? livePreviewIndices.inline
      : debouncedIndices.inline;

  const renderedCrosslineIndex =
    isLivePreviewing && draggingAxis === 'crossline'
      ? livePreviewIndices.crossline
      : debouncedIndices.crossline;

  const renderedTimeIndex =
    isLivePreviewing && draggingAxis === 'time'
      ? livePreviewIndices.time
      : timeRefreshMode === 'immediate'
        ? indices.time
        : timeRefreshMode === 'debounced'
          ? debouncedIndices.time
          : committedTimeIndex;

  const handleLoadState = useCallback((axis: SliceAxis, loading: boolean) => {
    setLoadingPlanes((prev) => ({ ...prev, [axis]: loading }));
  }, []);

  const handleTextureStats = useCallback((axis: SliceAxis, stats: SliceTextureStats) => {
    setTextureStats((prev) => ({ ...prev, [axis]: stats }));
  }, []);

  useEffect(() => {
    setSliceCacheLimit(cacheSize);
  }, [cacheSize]);

  useEffect(() => {
    if (timeRefreshMode !== 'onRelease') {
      setCommittedTimeIndex(indices.time);
    }
  }, [timeRefreshMode, indices.time]);

  const togglePlane = useCallback((axis: SliceAxis) => {
    setVisiblePlanes((prev) => ({ ...prev, [axis]: !prev[axis] }));
  }, []);

  const reloadPlane = useCallback((axis: SliceAxis) => {
    // Hard refresh: remove the currently displayed slice from the raw-slice cache,
    // then bump a nonce so the mounted SlicePlane effect runs again.
    // Without deleting the cache key, reload could simply repaint from cached data,
    // which is too subtle when a large pane failed to render cleanly.
    let dim = 0;
    let index = indices.inline;

    if (axis === 'crossline') {
      dim = 1;
      index = indices.crossline;
    } else if (axis === 'time') {
      dim = 2;
      index = indices.time;
    }

    sliceCache.delete(makeSliceCacheKey(zarrPath, dim, index));
    setPlaneReloadNonce((prev) => ({ ...prev, [axis]: prev[axis] + 1 }));
  }, [zarrPath, indices.inline, indices.crossline, indices.time]);

  const refreshBackendCacheInfo = useCallback(async () => {
    try {
      const info = await getBackendSliceCacheInfo();
      setBackendCacheInfo(info);
    } catch (err) {
      console.warn('Failed to read backend slice cache info', err);
      setBackendCacheInfo(null);
    }
  }, []);

  const clearSliceCacheAndRefresh = useCallback(async () => {
    // Clear frontend raw-slice cache, clear backend raw-slice cache if available,
    // then force visible panes to fetch/rebuild again so the user gets an immediate
    // visible result rather than a silent cache reset.
    sliceCache.clear();

    try {
      await clearBackendSliceCache();
      await refreshBackendCacheInfo();
    } catch (err) {
      console.warn('Failed to clear backend slice cache', err);
    }

    setPlaneReloadNonce((prev) => ({
      inline: prev.inline + (visiblePlanes.inline ? 1 : 0),
      crossline: prev.crossline + (visiblePlanes.crossline ? 1 : 0),
      time: prev.time + (visiblePlanes.time ? 1 : 0),
    }));
  }, [refreshBackendCacheInfo, visiblePlanes.inline, visiblePlanes.crossline, visiblePlanes.time]);

  const stepInline = useCallback((delta: number) => {
    setIndices((prev) => ({ ...prev, inline: clampIndex(prev.inline + delta, inlineCount - 1) }));
  }, [inlineCount]);

  const stepCrossline = useCallback((delta: number) => {
    setIndices((prev) => ({ ...prev, crossline: clampIndex(prev.crossline + delta, crosslineCount - 1) }));
  }, [crosslineCount]);

  const stepTime = useCallback((delta: number) => {
    setIndices((prev) => {
      const nextTime = clampIndex(prev.time + delta, timeCount - 1);
      if (timeRefreshMode === 'onRelease') setCommittedTimeIndex(nextTime);
      return { ...prev, time: nextTime };
    });
  }, [timeCount, timeRefreshMode]);

  const centerSlices = useCallback(() => {
    const centerInline = Math.floor((inlineCount - 1) / 2);
    const centerCrossline = Math.floor((crosslineCount - 1) / 2);
    const centerTime = Math.floor((timeCount - 1) / 2);

    setIndices({
      inline: centerInline,
      crossline: centerCrossline,
      time: centerTime,
    });
    setCommittedTimeIndex(centerTime);
  }, [inlineCount, crosslineCount, timeCount]);

  const handlePlaneDrag = useCallback((axis: SliceAxis, nextIndex: number) => {
    setIndices((prev) => {
      if (axis === 'inline') return { ...prev, inline: nextIndex };
      if (axis === 'crossline') return { ...prev, crossline: nextIndex };
      return { ...prev, time: nextIndex };
    });
  }, []);

  const handlePlaneDragState = useCallback((dragging: boolean, axis: SliceAxis) => {
    setPaneDragging(dragging);
    setDraggingAxis(dragging ? axis : null);

    if (!dragging && axis === 'time' && timeRefreshMode === 'onRelease') {
      setCommittedTimeIndex(indices.time);
    }
  }, [indices.time, timeRefreshMode]);

  useEffect(() => {
    let cancelled = false;
    // Avoid retaining old-volume slices after switching datasets.
    sliceCache.clear();

    if (emptyState) {
      const emptyShape = [100, 100, 100];
      setMetadata({ shape: emptyShape });
      setIndices({ inline: 49, crossline: 49, time: 49 });
      setCommittedTimeIndex(49);
      return () => {
        cancelled = true;
      };
    }

    async function loadMetadata() {
      const nextMetadata = await getZarrMetadata(zarrPath);
      if (cancelled) return;

      const [inlineCount, crosslineCount, timeCount] = nextMetadata.shape;
      setMetadata(nextMetadata);
      const centerInline = Math.floor((inlineCount - 1) / 2);
      const centerCrossline = Math.floor((crosslineCount - 1) / 2);
      const centerTime = Math.floor((timeCount - 1) / 2);

      setIndices({
        inline: centerInline,
        crossline: centerCrossline,
        time: centerTime,
      });
      setCommittedTimeIndex(centerTime);
    }

    loadMetadata().catch((err) => console.error('Failed to load metadata', err));

    return () => {
      cancelled = true;
    };
  }, [zarrPath, emptyState]);

  useEffect(() => {
    refreshBackendCacheInfo();
  }, [refreshBackendCacheInfo]);

  useEffect(() => {
    return () => {
      clearHorizontalRotationHold();
      clearVerticalRotationHold();
    };
  }, []);

  useEffect(() => {
    if (!sceneOverlaysModalOpen) return undefined;

    const handleSceneOverlaysModalKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        cancelSceneOverlaysModal();
      }
    };

    window.addEventListener('keydown', handleSceneOverlaysModalKeyDown);
    return () => window.removeEventListener('keydown', handleSceneOverlaysModalKeyDown);
  }, [sceneOverlaysModalOpen, cancelSceneOverlaysModal]);

  useEffect(() => {
    if (!sceneOverlaysModalOpen) return undefined;

    const keepSceneOverlaysModalInViewport = () => {
      const modal = sceneOverlaysModalRef.current;
      if (!modal) return;

      const rect = modal.getBoundingClientRect();
      let correctionX = 0;
      let correctionY = 0;

      if (rect.left < 0) correctionX = -rect.left;
      else if (rect.right > window.innerWidth) correctionX = window.innerWidth - rect.right;

      if (rect.top < 0) correctionY = -rect.top;
      else if (rect.bottom > window.innerHeight) correctionY = window.innerHeight - rect.bottom;

      if (correctionX !== 0 || correctionY !== 0) {
        setSceneOverlaysModalOffset((current) => ({
          x: current.x + correctionX,
          y: current.y + correctionY,
        }));
      }
    };

    window.addEventListener('resize', keepSceneOverlaysModalInViewport);
    return () => window.removeEventListener('resize', keepSceneOverlaysModalInViewport);
  }, [sceneOverlaysModalOpen]);

  useEffect(() => {
    if (activeControlTab !== 'performance') return;

    refreshBackendCacheInfo();
    const intervalId = window.setInterval(() => {
      refreshBackendCacheInfo();
    }, 5000);

    return () => window.clearInterval(intervalId);
  }, [activeControlTab, refreshBackendCacheInfo]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON'].includes(target.tagName)) return;

      if (event.key.toLowerCase() === 'r') {
        resetSceneView();
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  });


  const worldSize = useMemo<WorldSize>(() => {
    // Dynamic volume box: preserve the data aspect ratio instead of forcing
    // every dataset into a cube. Logical axis convention:
    // X=inline, Y=time/depth/sample, Z=crossline.
    const longestHorizontal = Math.max(inlineCount, crosslineCount);
    const base = 10;

    return {
      x: (inlineCount / longestHorizontal) * base,
      z: (crosslineCount / longestHorizontal) * base,
      y: (timeCount / longestHorizontal) * base * verticalExaggeration,
    };
  }, [inlineCount, crosslineCount, timeCount, verticalExaggeration]);

  const maxWorld = Math.max(worldSize.x, worldSize.y, worldSize.z);

  // Keep camera distance tied to the horizontal survey footprint only.
  // Vertical exaggeration changes worldSize.y; if cameraDistance also follows that,
  // React re-applies the camera position and the active view appears to reset.
  const cameraBaseWorld = Math.max(worldSize.x, worldSize.z);
  const cameraDistance = cameraBaseWorld * 1.8;

  if (!metadata) return <div>Loading metadata...</div>;

  const inlinePosition: [number, number, number] = [
    indexToWorld(indices.inline, inlineCount, worldSize.x),
    0,
    0,
  ];

  const crosslinePosition: [number, number, number] = [
    0,
    0,
    indexToWorld(indices.crossline, crosslineCount, worldSize.z),
  ];

  const timePosition: [number, number, number] = [
    0,
    indexToWorld(indices.time, timeCount, worldSize.y),
    0,
  ];

  function handleScenePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (!event.altKey || event.button !== 0) return;

    const target = event.target as HTMLElement | null;
    if (target && ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'LABEL'].includes(target.tagName)) return;

    // preventDefault removed: passive wheel listener warning avoidance
    event.stopPropagation();

    scenePanRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startOffsetX: sceneOffsetX,
      startOffsetY: sceneOffsetY,
    };

    event.currentTarget.setPointerCapture(event.pointerId);
    setPaneDragging(true);
  }

  function handleScenePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const pan = scenePanRef.current;
    if (!pan || pan.pointerId !== event.pointerId) return;

    // preventDefault removed: passive wheel listener warning avoidance
    event.stopPropagation();

    // Convert screen-pixel movement to a gentle world-space offset.
    // This moves the entire scene group, not the camera.
    const scale = Math.max(0.01, maxWorld / 700);
    setSceneOffsetX(pan.startOffsetX + (event.clientX - pan.startX) * scale);
    setSceneOffsetY(pan.startOffsetY - (event.clientY - pan.startY) * scale);
  }

  function handleScenePointerUp(event: React.PointerEvent<HTMLDivElement>) {
    const pan = scenePanRef.current;
    if (!pan || pan.pointerId !== event.pointerId) return;

    // preventDefault removed: passive wheel listener warning avoidance
    event.stopPropagation();

    scenePanRef.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
    setPaneDragging(false);
  }

  function getVolumeMaxIndex(dim: 0 | 1 | 2): number {
    if (dim === 0) return Math.max(0, inlineCount - 1);
    if (dim === 1) return Math.max(0, crosslineCount - 1);
    return Math.max(0, timeCount - 1);
  }

  function getVolumePageStepSize(): number {
    return useStepForPaging ? Math.max(1, Math.floor(volumeStep || 1)) : 1;
  }

  function clampVolumeIndex(index: number, dim: 0 | 1 | 2 = volumeRenderDim): number {
    return Math.max(0, Math.min(getVolumeMaxIndex(dim), Math.round(index)));
  }

  function stepVolumeCenterIndex(deltaPages: number) {
    const pageStep = getVolumePageStepSize();
    const maxIndex = getVolumeMaxIndex(volumeRenderDim);

    setVolumeCenterIndex((current) => {
      const next = current + deltaPages * pageStep;
      return Math.max(0, Math.min(maxIndex, next));
    });
  }

  function getViewerFacingStartIndex(dim: 0 | 1 | 2): number {
    // Camera starts from the positive X/Y/Z side.
    // Keep the active pane orientation unchanged; place it on the viewer-facing side.
    return getVolumeMaxIndex(dim);
  }

  function handleVolumeAltWheelZoom(deltaY: number) {
    const controls = controlsRef.current as any;
    const camera = controls?.object;

    if (!controls || !camera) return;

    const target = controls.target ?? new THREE.Vector3(0, 0, 0);
    const direction = new THREE.Vector3().subVectors(camera.position, target);
    const currentDistance = Math.max(0.001, direction.length());

    // Wheel down = zoom out; wheel up = zoom in.
    const zoomFactor = deltaY > 0 ? 1.10 : 0.90;
    const minDistance = Math.max(0.01, cameraDistance * 0.08);
    const maxDistance = Math.max(minDistance * 2, cameraDistance * 8);
    const nextDistance = Math.max(minDistance, Math.min(maxDistance, currentDistance * zoomFactor));

    direction.normalize().multiplyScalar(nextDistance);
    camera.position.copy(target).add(direction);
    camera.updateProjectionMatrix?.();
    controls.update?.();
  }

  function applyCameraView(
    multipliers: { x: number; y: number; z: number },
    distanceScale = 1,
  ) {
    const controls = controlsRef.current as any;
    const camera = controls?.object;

    if (!controls || !camera) return;

    camera.position.set(
      cameraDistance * multipliers.x * distanceScale,
      cameraDistance * multipliers.y * distanceScale,
      cameraDistance * multipliers.z * distanceScale,
    );

    controls.target.set(0, 0, 0);
    camera.updateProjectionMatrix?.();
    controls.update?.();
  }

  function getNavigationBaseDistance(): number {
    return Math.max(0.001, cameraDistance * Math.sqrt((1 * 1) + (0.8 * 0.8) + (1 * 1)));
  }

  function syncNavigationZoomPercent() {
    const controls = controlsRef.current as any;
    const camera = controls?.object;
    if (!controls || !camera) return;

    const currentDistance = Math.max(0.001, camera.position.distanceTo(controls.target));
    const nextPercent = THREE.MathUtils.clamp(
      Math.round((getNavigationBaseDistance() / currentDistance) * 100),
      25,
      800,
    );
    setNavigationZoomPercent(nextPercent);
  }

  function setNavigationZoomPercentValue(nextPercent: number) {
    const controls = controlsRef.current as any;
    const camera = controls?.object;
    if (!controls || !camera) return;

    const clampedPercent = THREE.MathUtils.clamp(Math.round(nextPercent), 25, 800);
    const target = controls.target.clone();
    const direction = new THREE.Vector3().subVectors(camera.position, target);
    if (direction.lengthSq() <= Number.EPSILON) direction.set(1, 0.8, 1);

    const nextDistance = getNavigationBaseDistance() / (clampedPercent / 100);
    direction.normalize().multiplyScalar(nextDistance);
    camera.position.copy(target).add(direction);
    camera.updateProjectionMatrix?.();
    controls.update?.();
    setNavigationZoomPercent(clampedPercent);
  }

  function stepNavigationZoom(direction: 'in' | 'out') {
    const factor = direction === 'in' ? 1.25 : 0.8;
    setNavigationZoomPercentValue(navigationZoomPercent * factor);
  }

  function applyNavigationOrientation(
    orientation: 'front' | 'right' | 'left' | 'back' | 'top',
  ) {
    const controls = controlsRef.current as any;
    const camera = controls?.object;
    if (!controls || !camera) return;

    const target = controls.target.clone();
    const currentDistance = Math.max(0.001, camera.position.distanceTo(target));

    if (orientation === 'top') {
      camera.up.set(0, 0, -1);
      camera.position.copy(target).add(new THREE.Vector3(0, currentDistance, 0));
    } else {
      camera.up.set(0, 1, 0);
      const direction = orientation === 'front'
        ? new THREE.Vector3(0, 0, 1)
        : orientation === 'right'
          ? new THREE.Vector3(1, 0, 0)
          : orientation === 'left'
            ? new THREE.Vector3(-1, 0, 0)
            : new THREE.Vector3(0, 0, -1);
      camera.position.copy(target).add(direction.multiplyScalar(currentDistance));
    }

    camera.lookAt(target);
    camera.updateProjectionMatrix?.();
    controls.update?.();
    setNavigationOrientation(orientation);
    syncNavigationZoomPercent();
  }

  function rotateNavigationCamera(axis: 'horizontal' | 'vertical', degrees: number) {
    const controls = controlsRef.current as any;
    const camera = controls?.object;
    if (!controls || !camera) return;

    const target = controls.target.clone();
    const offset = new THREE.Vector3().subVectors(camera.position, target);
    if (offset.lengthSq() <= Number.EPSILON) return;

    camera.up.set(0, 1, 0);
    const spherical = new THREE.Spherical().setFromVector3(offset);
    const radians = THREE.MathUtils.degToRad(degrees);

    if (axis === 'horizontal') {
      spherical.theta += radians;
    } else {
      spherical.phi = THREE.MathUtils.clamp(
        spherical.phi + radians,
        THREE.MathUtils.degToRad(2),
        Math.PI - THREE.MathUtils.degToRad(2),
      );
    }

    offset.setFromSpherical(spherical);
    camera.position.copy(target).add(offset);
    camera.lookAt(target);
    camera.updateProjectionMatrix?.();
    controls.update?.();
    setNavigationOrientation(null);
    syncNavigationZoomPercent();
  }

  function clearHorizontalRotationHold() {
    const hold = horizontalRotationHoldRef.current;
    if (hold.delay !== null) window.clearTimeout(hold.delay);
    if (hold.repeat !== null) window.clearInterval(hold.repeat);
    hold.delay = null;
    hold.repeat = null;
    hold.held = false;
  }

  function beginHorizontalRotationHold(
    direction: 'negative' | 'positive',
    event: React.PointerEvent<HTMLButtonElement>,
  ) {
    if (!horizontalRotationLocked) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    clearHorizontalRotationHold();
    const hold = horizontalRotationHoldRef.current;
    hold.held = false;
    hold.delay = window.setTimeout(() => {
      hold.held = true;
      rotateNavigationCamera('horizontal', direction === 'negative' ? -1 : 1);
      hold.repeat = window.setInterval(() => {
        rotateNavigationCamera('horizontal', direction === 'negative' ? -1 : 1);
      }, 24);
    }, 280);
  }

  function endHorizontalRotationHold(direction: 'negative' | 'positive') {
    const wasHeld = horizontalRotationHoldRef.current.held;
    clearHorizontalRotationHold();
    if (!wasHeld && horizontalRotationLocked) {
      rotateNavigationCamera('horizontal', direction === 'negative' ? -1 : 1);
    }
  }

  function clearVerticalRotationHold() {
    const hold = verticalRotationHoldRef.current;
    if (hold.delay !== null) window.clearTimeout(hold.delay);
    if (hold.repeat !== null) window.clearInterval(hold.repeat);
    hold.delay = null;
    hold.repeat = null;
    hold.held = false;
  }

  function beginVerticalRotationHold(
    direction: 'negative' | 'positive',
    event: React.PointerEvent<HTMLButtonElement>,
  ) {
    if (!verticalRotationLocked) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    clearVerticalRotationHold();
    const hold = verticalRotationHoldRef.current;
    hold.held = false;
    hold.delay = window.setTimeout(() => {
      hold.held = true;
      rotateNavigationCamera('vertical', direction === 'negative' ? -1 : 1);
      hold.repeat = window.setInterval(() => {
        rotateNavigationCamera('vertical', direction === 'negative' ? -1 : 1);
      }, 24);
    }, 280);
  }

  function endVerticalRotationHold(direction: 'negative' | 'positive') {
    const wasHeld = verticalRotationHoldRef.current.held;
    clearVerticalRotationHold();
    if (!wasHeld && verticalRotationLocked) {
      rotateNavigationCamera('vertical', direction === 'negative' ? -1 : 1);
    }
  }

  function captureCurrentSceneView(): SavedSceneView | null {
    const controls = controlsRef.current as any;
    const camera = controls?.object;

    if (!controls || !camera) return null;

    return {
      cameraPosition: [camera.position.x, camera.position.y, camera.position.z],
      cameraTarget: [controls.target.x, controls.target.y, controls.target.z],
      sceneOffsetX,
      sceneOffsetY,
    };
  }

  function applySavedSceneView(scene: SavedSceneView) {
    const controls = controlsRef.current as any;
    const camera = controls?.object;

    if (!controls || !camera) return;

    scenePanRef.current = null;
    setPaneDragging(false);
    setSceneOffsetX(scene.sceneOffsetX);
    setSceneOffsetY(scene.sceneOffsetY);

    camera.position.set(...scene.cameraPosition);
    controls.target.set(...scene.cameraTarget);
    camera.updateProjectionMatrix?.();
    controls.update?.();
  }

  function setSceneView() {
    const scene = captureCurrentSceneView();
    if (!scene) return;
    setSavedSceneView(scene);
  }

  function returnSceneView() {
    if (!savedSceneView) return;
    applySavedSceneView(savedSceneView);
  }

  function resetSceneView() {
    // Reset to the default 3D recovery state:
    // - clear stored Set Scene memory
    // - restore default camera/orbit
    // - restore single inline pane display
    // - hide volume-stack rendering
    // Preserve loaded data, slice indices, cache state, amplitude/color, and metadata.
    setSavedSceneView(null);
    scenePanRef.current = null;
    setPaneDragging(false);
    setSceneOffsetX(0);
    setSceneOffsetY(0);
    setVisiblePlanes({ inline: true, crossline: false, time: false });
    setVolumeStackEnabled(false);
    setVolumeBackgroundMode('off');
    setVolumeCacheStatus(null);
    applyCameraView({ x: 1, y: 0.8, z: 1 }, 1);
    setNavigationZoomPercent(100);
    setNavigationOrientation(null);
  }

  function setTimeDirectionCameraView() {
    // Time/depth slices are horizontal. When switching to Time direction,
    // use an oblique top-facing camera angle so the active slice is visible
    // as a surface, not edge-on.
    applyCameraView({ x: 0.85, y: 1.25, z: 0.85 }, 1);
  }

  function handleViewerWheel(event: React.WheelEvent<HTMLDivElement>) {
    // Keep plane movement and volume movement separate.
    // Mouse-wheel volume scrolling is only active while the Volume tab is selected.
    // If the user is working in View / Planes / Amplitude / Performance, do not intercept the wheel.
    if (
      !volumeStackEnabled ||
      !volumeWheelScrollEnabled ||
      activeControlTab !== 'volume'
    ) {
      return;
    }

    // Option/Alt + wheel zooms the camera while mouse-wheel volume scrolling is enabled.
    // Handle it directly instead of relying on OrbitControls receiving the wheel event.
    if (event.altKey) {
      event.stopPropagation();
      handleVolumeAltWheelZoom(event.deltaY);
      return;
    }

    // preventDefault removed: passive wheel listener warning avoidance
    event.stopPropagation();

    const direction = event.deltaY > 0 ? 1 : -1;
    const multiplier = event.shiftKey ? 10 : 1;

    // When Use Step for Paging is enabled, the active pane moves by Page Step.
    // When disabled, it moves one slice at a time.
    stepVolumeCenterIndex(direction * multiplier);
  }

  return (
    <div
      className={`mv-sdv3d-viewer mv-sdv3d-wbv-parity${menuCollapsed ? ' mv-sdv3d-controls-collapsed' : ''}${infoCollapsed ? ' mv-sdv3d-info-collapsed' : ''}`}
      style={{
        width: '100%',
        height: '100%',
        background: canvasBackground,
        position: 'relative',
        overflow: 'hidden',
        overscrollBehavior: 'none',
        touchAction: 'none',
        contain: 'layout paint size',
      }}
      onPointerDownCapture={handleScenePointerDown}
      onPointerMoveCapture={handleScenePointerMove}
      onPointerUpCapture={handleScenePointerUp}
      onPointerCancelCapture={handleScenePointerUp}
      onWheelCapture={handleViewerWheel}
    >
      <Canvas dpr={[1, 2]} gl={{ antialias: true }} style={{ background: canvasBackground }}>
        <PerspectiveCamera makeDefault position={[cameraDistance, cameraDistance * 0.8, cameraDistance]} fov={50} />
        <OrbitControls
          ref={controlsRef}
          makeDefault
          enabled={!paneDragging}
          onChange={syncNavigationZoomPercent}
          onStart={() => setNavigationOrientation(null)}
        />
        <SdvCompassCameraSync
          compassRoseRef={compassRoseRef}
          compassAngleRef={compassAngleRef}
        />
        <ambientLight intensity={0.5} />
        <pointLight position={[10, 10, 10]} />

        <group position={[sceneOffsetX, sceneOffsetY, 0]}>
        {activeSceneOverlayVisibility.bounds && (
          <VolumeBounds
            worldSize={worldSize}
            color={sceneOverlayBoundingBoxColor}
            adaptive={canvasShadeAdaptive}
            opacityOverride={sceneOverlayBoundingBoxOpacity}
          />
        )}

        {/* Inline Slice: fixed X, spans crossline(Z) by time(Y). */}
        {!emptyState && visiblePlanes.inline && (
          <SlicePlane
            zarrPath={zarrPath}
            dim={0}
            index={renderedInlineIndex}
            maxIndex={inlineCount - 1}
            axis="inline"
            position={inlinePosition}
            rotation={[0, Math.PI / 2, 0]}
            planeSize={[worldSize.z, worldSize.y]}
            colorMap={colorMap}
            textureScale={effectiveTextureScale}
            reloadNonce={planeReloadNonce.inline}
            amplitudeGain={debouncedAmplitudeGain}
            clipPercentile={debouncedClipPercentile}
            waveDisplayMode={waveDisplayMode}
            flipAxis0={true}
            onLoadState={handleLoadState}
            onTextureStats={handleTextureStats}
            onPlaneDrag={handlePlaneDrag}
            onPlaneDragState={handlePlaneDragState}
            dragCount={inlineCount}
            dragWorldSize={worldSize.x}
            dragAxisVector={[1, 0, 0]}
          />
        )}

        {/* Crossline Slice: fixed Z, spans inline(X) by time(Y). */}
        {!emptyState && visiblePlanes.crossline && (
          <SlicePlane
            zarrPath={zarrPath}
            dim={1}
            index={renderedCrosslineIndex}
            maxIndex={crosslineCount - 1}
            axis="crossline"
            position={crosslinePosition}
            rotation={[0, 0, 0]}
            planeSize={[worldSize.x, worldSize.y]}
            colorMap={colorMap}
            textureScale={effectiveTextureScale}
            reloadNonce={planeReloadNonce.crossline}
            amplitudeGain={debouncedAmplitudeGain}
            clipPercentile={debouncedClipPercentile}
            waveDisplayMode={waveDisplayMode}
            onLoadState={handleLoadState}
            onTextureStats={handleTextureStats}
            onPlaneDrag={handlePlaneDrag}
            onPlaneDragState={handlePlaneDragState}
            dragCount={crosslineCount}
            dragWorldSize={worldSize.z}
            dragAxisVector={[0, 0, 1]}
          />
        )}

        {/* Time/depth Slice: fixed Y, spans inline(X) by crossline(Z). */}
        {!emptyState && visiblePlanes.time && (
          <SlicePlane
            zarrPath={zarrPath}
            dim={2}
            index={renderedTimeIndex}
            maxIndex={timeCount - 1}
            axis="time"
            position={timePosition}
            rotation={[-Math.PI / 2, 0, 0]}
            planeSize={[worldSize.x, worldSize.z]}
            colorMap={colorMap}
            textureScale={effectiveTextureScale}
            reloadNonce={planeReloadNonce.time}
            amplitudeGain={debouncedAmplitudeGain}
            clipPercentile={debouncedClipPercentile}
            waveDisplayMode={waveDisplayMode}
            flipAxis1={true}
            onLoadState={handleLoadState}
            onTextureStats={handleTextureStats}
            onPlaneDrag={handlePlaneDrag}
            onPlaneDragState={handlePlaneDragState}
            dragCount={timeCount}
            dragWorldSize={worldSize.y}
            dragAxisVector={[0, 1, 0]}
          />
        )}
{!emptyState && volumeStackEnabled && (
          <VolumePagedRenderer
            zarrPath={zarrPath}
            dim={volumeRenderDim}
            centerIndex={volumeCenterIndex}
            maxIndex={Math.max(
              0,
              volumeRenderDim === 0
                ? inlineCount - 1
                : volumeRenderDim === 1
                  ? crosslineCount - 1
                  : timeCount - 1
            )}
            windowSize={volumeWindowSize}
            step={volumeStep}
            useStepForPaging={useStepForPaging}
            extentMode={volumeExtentMode}
            quality={volumeQuality}
            backgroundMode={volumeBackgroundMode}
            opacity={volumeOpacity}
            density={volumeDensity}
            threshold={volumeThreshold}
            amplitudeGain={debouncedAmplitudeGain}
            clipPercentile={debouncedClipPercentile}
            colorMap={colorMap}
            waveDisplayMode={waveDisplayMode}
            worldSize={worldSize}
            onCacheStatus={setVolumeCacheStatus}
            loadDirectionRequest={directionLoadRequest}
            pauseDirectionRequest={directionPauseRequest}
            unloadDirectionRequest={directionUnloadRequest}
            onDirectionLoadStatus={setDirectionLoadStatus}
          />
        )}

        {activeSceneOverlayVisibility.grid && (
          canvasShadeAdaptive || sceneOverlayGridColor ? (
            <SceneOpacityGrid
              overlayOpacity={sceneOverlayGridOpacity}
              args={[Math.max(10, maxWorld * 1.5), Math.max(10, Math.round(maxWorld * 1.5))]}
              fadeDistance={25}
              cellColor={sceneOverlayGridColor ?? canvasGridColor}
              sectionColor={sceneOverlayGridColor ?? canvasGridColor}
            />
          ) : (
            <SceneOpacityGrid
              overlayOpacity={sceneOverlayGridOpacity}
              args={[Math.max(10, maxWorld * 1.5), Math.max(10, Math.round(maxWorld * 1.5))]}
              fadeDistance={25}
            />
          )
        )}
        {activeSceneOverlayVisibility.axes && (
          canvasShadeAdaptive ? (
            <ShadeAwareAxesHelper
              size={Math.max(3, maxWorld * 0.6) * sceneOverlayAxisScale}
              shadeId={canvasShadeId}
            />
          ) : (
            <axesHelper args={[Math.max(3, maxWorld * 0.6) * sceneOverlayAxisScale]} />
          )
        )}

        {activeSceneOverlayVisibility.bounds && activeSceneOverlayVisibility.labels && (
          <AxisRulerLabels
            worldSize={worldSize}
            volume={volume}
            inlineCount={inlineCount}
            crosslineCount={crosslineCount}
            timeCount={timeCount}
            color={sceneOverlayLabelColor}
            adaptive={canvasShadeAdaptive}
            sizeScale={sceneOverlayLabelSizeScale}
            opacityScale={sceneOverlayLabelOpacityScale}
          />
        )}
        </group>
      </Canvas>
      {activeSceneOverlayVisibility.compass && (
        <div
          className="mv-sdv3d-wbv-compass-dial"
          aria-label="Viewer orientation compass"
          style={{
            '--wbv-compass-surface': compassPalette.surface,
            '--wbv-compass-border': compassPalette.border,
            '--wbv-compass-text': compassPalette.text,
            '--wbv-compass-north': compassPalette.north,
            transform: `scale(${sceneOverlayCompassSizeScale})`,
            transformOrigin: 'top left',
            opacity: sceneOverlayCompassOpacity,
          } as React.CSSProperties}
        >
          <div className="mv-sdv3d-wbv-compass-dial__bezel" aria-hidden="true">
            <span className="mv-sdv3d-wbv-compass-dial__viewer-eye">
              <svg viewBox="0 0 24 16" focusable="false" aria-hidden="true">
                <path d="M1.5 8C4.3 3.7 7.8 1.5 12 1.5S19.7 3.7 22.5 8C19.7 12.3 16.2 14.5 12 14.5S4.3 12.3 1.5 8Z" />
                <circle cx="12" cy="8" r="3.15" />
                <circle className="mv-sdv3d-wbv-compass-dial__viewer-eye-highlight" cx="13" cy="7" r="0.75" />
              </svg>
            </span>
            <div ref={compassRoseRef} className="mv-sdv3d-wbv-compass-dial__rose">
              <span className="mv-sdv3d-wbv-compass-dial__cardinal is-north">N</span>
              <span className="mv-sdv3d-wbv-compass-dial__cardinal is-east">E</span>
              <span className="mv-sdv3d-wbv-compass-dial__cardinal is-south">S</span>
              <span className="mv-sdv3d-wbv-compass-dial__cardinal is-west">W</span>
              <span className="mv-sdv3d-wbv-compass-dial__center" />
            </div>
          </div>
        </div>
      )}
      


      {emptyState && (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: 'absolute',
            left: '50%',
            top: '50%',
            transform: 'translate(-50%, -50%)',
            zIndex: 20,
            padding: '10px 16px',
            borderRadius: 6,
            border: '1px solid var(--mv-border-strong)',
            background: 'color-mix(in srgb, var(--mv-surface-1) 92%, transparent)',
            color: 'var(--mv-text-primary)',
            fontFamily: 'var(--mv-font-ui)',
            fontSize: '0.82rem',
            fontWeight: 600,
            pointerEvents: 'none',
          }}
        >
          {emptyStateMessage}
        </div>
      )}

      {volumeCacheStatus?.loading && (
        <div
          style={{
            position: 'absolute',
            left: '50%',
            top: 18,
            transform: 'translateX(-50%)',
            background: 'rgba(0, 0, 0, 0.82)',
            color: 'var(--mv-text-primary)',
            border: '1px solid var(--mv-border-strong)',
            borderRadius: 8,
            padding: '9px 14px',
            fontSize: 13,
            fontWeight: 600,
            letterSpacing: 0.2,
            zIndex: 20,
            pointerEvents: 'none',
            boxShadow: '0 4px 14px rgba(0,0,0,0.35)',
          }}
        >
          {volumeCacheStatus.message}
        </div>
      )}

      <div
        onPointerDown={(e) => e.stopPropagation()}
        onPointerMove={(e) => e.stopPropagation()}
        onPointerUp={(e) => e.stopPropagation()}
        onWheel={(e) => e.stopPropagation()}
        className="mv-viewer-info-stack mv-sdv3d-wbv-info-panel"
        style={{
          position: 'absolute',
          top: 0,
          right: 0,
          width: 300,
          maxHeight: 'calc(100% - 20px)',
          zIndex: 12,
          color: 'var(--mv-text-primary)',
          pointerEvents: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          fontVariantNumeric: 'tabular-nums',
          contain: 'layout paint',
          transform: infoCollapsed ? 'translateX(calc(100% + 10px))' : 'translateX(0)',
          transition: 'transform 180ms ease',
          pointerEvents: infoCollapsed ? 'none' : 'auto',
        }}
      >
        <button
          className="mv-viewer-compact-button mv-viewer-info-collapse-button"
          onClick={() => setInfoCollapsed(true)}
          style={{
            position: 'absolute',
            top: 8,
            left: 8,
            background: 'var(--mv-surface-3)',
            color: 'var(--mv-text-primary)',
            border: '1px solid var(--mv-border-strong)',
            padding: '2px 7px',
            cursor: 'pointer',
          }}
          title="Collapse information panel"
          aria-label="Collapse information panel"
        >
          ▶
        </button>

        <h3
          className="mv-viewer-controls-title mv-viewer-info-primary-heading"
          style={{ margin: 0, width: '100%', padding: '0 34px', textAlign: 'center', boxSizing: 'border-box' }}
        >
          Volume Info
        </h3>

        <div
          className="mv-viewer-info-togglebar"
          style={{
            background: 'transparent',
            border: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-start',
            gap: 14,
          }}
        >
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="checkbox"
              checked={showVolumeInfo}
              onChange={(e) => setShowVolumeInfo(e.target.checked)}
            />
            Volume info
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="checkbox"
              checked={showSliceInfo}
              onChange={(e) => setShowSliceInfo(e.target.checked)}
            />
            Slice info
          </label>
        </div>

        {(showVolumeInfo || showSliceInfo) && (
          <div
            style={{
              overflowY: 'auto',
              height: 'calc(100vh - 92px)',
              maxHeight: 'calc(100vh - 92px)',
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
              overscrollBehavior: 'contain',
              scrollbarGutter: 'stable',
            }}
          >
            {emptyState ? (
              <aside
                className="mv-viewer-info-card"
                style={{
                  boxSizing: 'border-box',
                  padding: '12px',
                }}
              >
                <div
                  style={{
                    color: 'var(--mv-text-primary)',
                    fontFamily: 'var(--mv-font-ui)',
                    fontSize: '0.76rem',
                    fontWeight: 400,
                    lineHeight: 1.2,
                  }}
                >
                  {emptyStateMessage}
                </div>
              </aside>
            ) : (
              <>
            {showVolumeInfo && (
              <aside
                className="mv-viewer-info-card"
                style={{
                  boxSizing: 'border-box',
                }}
              >
                <div className="mv-type-property-grid mv-sdv3d-metadata-grid" style={{ display: 'grid' }}>
                  <div className="mv-sdv3d-metadata-label">Dataset</div>
                  <div className="mv-type-property-value" style={{ wordBreak: 'break-word' }}>{zarrPath}</div>

                  <div className="mv-sdv3d-metadata-label">Shape</div>
                  <div className="mv-type-property-value">{inlineCount} × {crosslineCount} × {timeCount}</div>

                  <div className="mv-sdv3d-metadata-label">Inline range</div>
                  <div className="mv-type-property-value">0 – {Math.max(0, inlineCount - 1)}</div>

                  <div className="mv-sdv3d-metadata-label">Crossline range</div>
                  <div className="mv-type-property-value">0 – {Math.max(0, crosslineCount - 1)}</div>

                  <div className="mv-sdv3d-metadata-label">Time range</div>
                  <div className="mv-type-property-value">0 – {Math.max(0, timeCount - 1)}</div>

                  <div className="mv-sdv3d-metadata-label">World box</div>
                  <div className="mv-type-property-value">X {worldSize.x.toFixed(2)} · Y {worldSize.y.toFixed(2)} · Z {worldSize.z.toFixed(2)}</div>

                  <div className="mv-sdv3d-metadata-label">Visible planes</div>
                  <div className="mv-type-property-value">
                    {[
                      visiblePlanes.inline ? 'Inline' : null,
                      visiblePlanes.crossline ? 'Crossline' : null,
                      visiblePlanes.time ? 'Time' : null,
                    ].filter(Boolean).join(', ') || 'None'}
                  </div>

                  <div className="mv-sdv3d-metadata-label">Frontend cache</div>
                  <div className="mv-type-property-value">{sliceCache.size} / {cacheSize} slices</div>

                  <div className="mv-sdv3d-metadata-label">Backend cache</div>
                  <div className="mv-type-property-value">
                    {backendCacheInfo
                      ? `${backendCacheInfo.entries} entries · ${(backendCacheInfo.bytes / 1048576).toFixed(1)} MB`
                      : 'not available'}
                  </div>
                </div>
              </aside>
            )}

            {showSliceInfo && (
              <aside
                className="mv-viewer-info-card"
                style={{
                  boxSizing: 'border-box',
                }}
              >
                <div className="mv-type-section-heading" style={{ marginBottom: 8 }}>
                  Slice Info
                </div>

                <div className="mv-type-property-grid mv-sdv3d-metadata-grid" style={{ display: 'grid' }}>
                  <div className="mv-sdv3d-metadata-label">Mode</div>
                  <div className="mv-type-property-value">{volumeStackEnabled ? 'Volume stack' : 'Slice planes'}</div>

                  <div className="mv-sdv3d-metadata-label">Active axis</div>
                  <div className="mv-type-property-value">
                    {volumeStackEnabled
                      ? volumeRenderDim === 0
                        ? 'Inline'
                        : volumeRenderDim === 1
                          ? 'Crossline'
                          : 'Time/depth'
                      : 'Planes'}
                  </div>

                  <div className="mv-sdv3d-metadata-label">Inline</div>
                  <div className="mv-type-property-value">
                    {volumeStackEnabled && volumeRenderDim === 0
                      ? `${volumeCenterIndex} / ${Math.max(0, inlineCount - 1)}`
                      : `${indices.inline} / ${Math.max(0, inlineCount - 1)}`}
                  </div>

                  <div className="mv-sdv3d-metadata-label">Crossline</div>
                  <div className="mv-type-property-value">
                    {volumeStackEnabled && volumeRenderDim === 1
                      ? `${volumeCenterIndex} / ${Math.max(0, crosslineCount - 1)}`
                      : `${indices.crossline} / ${Math.max(0, crosslineCount - 1)}`}
                  </div>

                  <div className="mv-sdv3d-metadata-label">Time/depth</div>
                  <div className="mv-type-property-value">
                    {volumeStackEnabled && volumeRenderDim === 2
                      ? `${volumeCenterIndex} / ${Math.max(0, timeCount - 1)}`
                      : `${indices.time} / ${Math.max(0, timeCount - 1)}`}
                  </div>

                  <div className="mv-sdv3d-metadata-label">Rendered time</div>
                  <div className="mv-type-property-value">{renderedTimeIndex}</div>

                  <div className="mv-sdv3d-metadata-label">Color map</div>
                  <div className="mv-type-property-value">{colorMap}</div>

                  <div className="mv-sdv3d-metadata-label">Wave mode</div>
                  <div className="mv-type-property-value">{waveDisplayMode}</div>

                  <div className="mv-sdv3d-metadata-label">Gain</div>
                  <div className="mv-type-property-value">{amplitudeGain.toFixed(2)}×</div>

                  <div className="mv-sdv3d-metadata-label">Clip</div>
                  <div className="mv-type-property-value">{clipPercentile.toFixed(1)}%</div>

                  <div className="mv-sdv3d-metadata-label">Slice detail</div>
                  <div className="mv-type-property-value">{textureScale === 1 ? 'Native' : `${textureScale.toFixed(2)}×`} selected · {effectiveTextureScale === 1 ? 'Native' : `${effectiveTextureScale.toFixed(2)}×`} active · {activeTextureDetailMode}</div>

                  {activeTextureStats && (
                    <>
                      <div className="mv-sdv3d-metadata-label">Texture size</div>
                      <div className="mv-type-property-value">{activeTextureStats.textureWidth} × {activeTextureStats.textureHeight} px</div>

                      <div className="mv-sdv3d-metadata-label">Source slice</div>
                      <div className="mv-type-property-value">{activeTextureStats.sourceWidth} × {activeTextureStats.sourceHeight} samples</div>

                      <div className="mv-sdv3d-metadata-label">Texture render</div>
                      <div className="mv-type-property-value">{activeTextureStats.renderMs.toFixed(0)} ms · {(activeTextureStats.texturePixels / 1000000).toFixed(2)} MP</div>
                    </>
                  )}

                  <div className="mv-sdv3d-metadata-label">Active window</div>
                  <div className="mv-type-property-value">{activeDiagnosticAxis} @ {activeDiagnosticSliceIndex} · whole-slice baseline</div>

                  <div className="mv-sdv3d-metadata-label">Source axes</div>
                  <div className="mv-type-property-value">fixed {activeDiagnosticAxisMapping.fixedAxis} · x {activeDiagnosticAxisMapping.sourceXAxis} · y {activeDiagnosticAxisMapping.sourceYAxis}</div>

                  <div className="mv-sdv3d-metadata-label">Source bounds</div>
                  <div className="mv-type-property-value">{formatActive3DSourceBounds(activeDiagnosticSourceBounds)}</div>

                  <div className="mv-sdv3d-metadata-label">Future request</div>
                  <div className="mv-type-property-value">{activeDiagnosticRequest.outputShape.width} × {activeDiagnosticRequest.outputShape.height} · {activeDiagnosticRequest.quality}</div>

                  <div className="mv-sdv3d-metadata-label">Future cache key</div>
                  <div className="mv-type-property-value" title={activeDiagnosticCacheKey}>{activeDiagnosticCacheKey.slice(0, 48)}…</div>

                  <div className="mv-sdv3d-metadata-label">Vertical exag.</div>
                  <div className="mv-type-property-value">{verticalExaggeration.toFixed(1)}×</div>

                  <div className="mv-sdv3d-metadata-label">Loading</div>
                  <div className="mv-type-property-value">
                    Inline {loadingPlanes.inline ? 'loading' : 'idle'} · Crossline {loadingPlanes.crossline ? 'loading' : 'idle'} · Time {loadingPlanes.time ? 'loading' : 'idle'}
                  </div>

                  <div className="mv-sdv3d-metadata-label">Volume stack</div>
                  <div className="mv-type-property-value">{volumeStackEnabled ? `On · center ${volumeCenterIndex}` : 'Off'}</div>

                  {volumeStackEnabled && (
                    <>
                      <div className="mv-sdv3d-metadata-label">Stack dir.</div>
                      <div className="mv-type-property-value">{volumeRenderDim === 0 ? 'Inline' : volumeRenderDim === 1 ? 'Crossline' : 'Time/depth'}</div>

                      <div className="mv-sdv3d-metadata-label">Stack center</div>
                      <div className="mv-type-property-value">{volumeCenterIndex}</div>

                      <div className="mv-sdv3d-metadata-label">Window / step</div>
                      <div className="mv-type-property-value">{volumeWindowSize} / {volumeStep}</div>

                      <div className="mv-sdv3d-metadata-label">Quality</div>
                      <div className="mv-type-property-value">{volumeQuality}</div>

                      <div className="mv-sdv3d-metadata-label">Opacity</div>
                      <div className="mv-type-property-value">{volumeOpacity.toFixed(2)}</div>

                      <div className="mv-sdv3d-metadata-label">Density</div>
                      <div className="mv-type-property-value">{volumeDensity.toFixed(2)}×</div>

                      <div className="mv-sdv3d-metadata-label">Threshold</div>
                      <div className="mv-type-property-value">{volumeThreshold.toFixed(3)}</div>
                    </>
                  )}
                </div>
              </aside>
            )}
              </>
            )}
          </div>
        )}
      </div>

      <div
        className="mv-viewer-controls-panel mv-viewer-controls-panel--info-parity mv-sdv3d-wbv-controls-panel"
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: 300,
          padding: 12,
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          transform: menuCollapsed ? 'translateX(calc(-100% - 10px))' : 'translateX(0)',
          transition: 'transform 180ms ease',
          pointerEvents: menuCollapsed ? 'none' : 'auto',
        }}
      >
        <button
          className="mv-viewer-compact-button"
          onClick={() => setMenuCollapsed(true)}
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            background: 'var(--mv-surface-3)',
            color: 'var(--mv-text-primary)',
            border: '1px solid var(--mv-border-strong)',
            padding: '2px 7px',
            cursor: 'pointer',
          }}
          title="Collapse controls"
        >
          ◀
        </button>
        <h3
          className="mv-viewer-controls-title"
          style={{ margin: 0, width: '100%', padding: '0 34px', textAlign: 'center', boxSizing: 'border-box' }}
        >
          3D View Controls
        </h3>
        <div className="mv-viewer-controls-meta">
          X=Inline · Y=Time/Depth · Z=Crossline
        </div>
        <div className="mv-viewer-controls-meta">
          Data shape: {inlineCount} × {crosslineCount} × {timeCount}
        </div>
        <div className="mv-viewer-controls-meta">
          World box: X {worldSize.x.toFixed(2)} · Y {worldSize.y.toFixed(2)} · Z {worldSize.z.toFixed(2)}
        </div>

        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', borderTop: '1px solid var(--mv-border-normal)', paddingTop: 8 }}>
          {([
            ['view', 'View'],
            ['planes', 'Planes'],
            ['volume', 'Volume'],
            ['amplitude', 'Amplitude'],
            ['performance', 'Performance'],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setActiveControlTab(key)}
              className={`mv-viewer-tab${activeControlTab === key ? ' mv-viewer-tab--active' : ''}`}
              style={{
                cursor: 'pointer',
              }}
            >
              {label}
            </button>
          ))}
          <button
            type="button"
            className="mv-viewer-tab"
            style={{ cursor: 'pointer', gridColumn: 3, gridRow: 2 }}
            onClick={() => setSceneOverlaysInfoOpen((open) => !open)}
            aria-label="Scene Overlays information"
            aria-expanded={sceneOverlaysInfoOpen}
            title="Scene Overlays information"
          >
            <span className="mv-sdv-info-badge" aria-hidden="true">i</span>
          </button>
        </div>

        {activeControlTab === 'view' && (
          <>
            <div className="mv-sdv-info-section mv-sdv-scene-overlays-section" style={{ borderTop: '1px solid var(--mv-border-normal)', paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 6, paddingBottom: '0.52rem' }}>
              <div className="mv-sdv-control-subheading mv-sdv-info-heading">
                <span>Scene Overlays</span>
                <button
                  type="button"
                  className="mv-sdv3d-scene-overlays-gear"
                  aria-label="Scene Overlays settings"
                  aria-haspopup="dialog"
                  title="Scene Overlays settings"
                  onClick={openSceneOverlaysModal}
                  style={{
                    marginLeft: 'auto',
                    marginRight: 'calc(100% - (264px + 0.56rem))',
                    width: '16px',
                    height: '16px',
                    minWidth: '16px',
                    padding: 0,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    border: 0,
                    background: 'transparent',
                    color: 'var(--mv-role-text-secondary)',
                    fontFamily: 'var(--mv-font-ui)',
                    fontSize: '16px',
                    lineHeight: 1,
                    cursor: 'pointer',
                  }}
                >
                  <svg
                    aria-hidden="true"
                    viewBox="0 0 24 24"
                    width="16"
                    height="16"
                    style={{ display: 'block', flex: '0 0 16px' }}
                  >
                    <path
                      fill="currentColor"
                      d="M19.14 12.94c.04-.31.06-.63.06-.94s-.02-.63-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.62l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96a7.12 7.12 0 0 0-1.62-.94L14.4 2.8a.48.48 0 0 0-.48-.4h-3.84a.48.48 0 0 0-.48.4l-.36 2.54c-.59.24-1.13.55-1.62.94l-2.39-.96a.49.49 0 0 0-.59.22L2.72 8.86a.49.49 0 0 0 .12.62l2.03 1.58c-.05.31-.07.65-.07.94 0 .31.02.63.07.94l-2.03 1.58a.49.49 0 0 0-.12.62l1.92 3.32c.12.22.38.31.59.22l2.39-.96c.49.39 1.03.71 1.62.94l.36 2.54c.04.24.24.4.48.4h3.84c.24 0 .44-.16.48-.4l.36-2.54c.59-.24 1.13-.55 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32a.49.49 0 0 0-.12-.62l-2.02-1.58ZM12 15.5A3.5 3.5 0 1 1 12 8a3.5 3.5 0 0 1 0 7.5Z"
                    />
                  </svg>
                </button>
              </div>
              {sceneOverlaysInfoOpen && (
                <div className="mv-sdv-info-popover" role="note">
                  Shift + left-drag directly on a pane to move it through the volume. Orbit is disabled while dragging.
                </div>
              )}
              <label><input type="checkbox" checked={showGrid} onChange={() => setShowGrid((v) => !v)} /> Horizontal grid</label>
              <label><input type="checkbox" checked={showBounds} onChange={() => setShowBounds((v) => !v)} /> Bounding box</label>
              <label><input type="checkbox" checked={showAxes} onChange={() => setShowAxes((v) => !v)} /> X/Y/Z axis lines</label>
              <label><input type="checkbox" checked={showAxisLabels} onChange={() => setShowAxisLabels((v) => !v)} /> Axis labels</label>
              <label><input type="checkbox" checked={showCompass} onChange={() => setShowCompass((v) => !v)} /> Compass</label>
            </div>
            <div
              className="mv-sdv-info-section mv-sdv3d-navigation-section"
              style={{ borderTop: '1px solid var(--mv-border-normal)', paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}
            >
              <div className="mv-sdv-control-subheading mv-sdv-info-heading">
                <span>View</span>
              </div>

              <div className="mv-sdv3d-navigation-controls">
                <div className="mv-sdv3d-navigation-block">
                  <h4>Orientation</h4>
                  <div className="mv-sdv3d-navigation-orientation-grid">
                    {([
                      ['front', 'F', 'Front view'],
                      ['right', 'R', 'Right view'],
                      ['left', 'L', 'Left view'],
                      ['back', 'BK', 'Back view'],
                      ['top', 'T', 'Top view'],
                    ] as const).map(([orientation, label, title]) => (
                      <button
                        key={orientation}
                        type="button"
                        className={navigationOrientation === orientation ? 'is-active' : ''}
                        aria-pressed={navigationOrientation === orientation}
                        title={title}
                        onClick={() => applyNavigationOrientation(orientation)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="mv-sdv3d-navigation-block">
                  <h4>Zoom</h4>
                  <div className="mv-sdv3d-navigation-three-column">
                    <button
                      type="button"
                      aria-label="Zoom out"
                      disabled={navigationZoomPercent <= 25}
                      onClick={() => stepNavigationZoom('out')}
                    >
                      −
                    </button>
                    <button
                      type="button"
                      className="mv-sdv3d-navigation-value"
                      title="Reset zoom to 100%"
                      onClick={() => setNavigationZoomPercentValue(100)}
                    >
                      {navigationZoomPercent}%
                    </button>
                    <button
                      type="button"
                      aria-label="Zoom in"
                      disabled={navigationZoomPercent >= 800}
                      onClick={() => stepNavigationZoom('in')}
                    >
                      +
                    </button>
                  </div>
                </div>

                <div className="mv-sdv3d-navigation-block mv-sdv3d-navigation-rotation-block">
                  <h4>Rotation</h4>
                  <div className="mv-sdv3d-navigation-three-column">
                    <button
                      type="button"
                      aria-label="Rotate horizontally negative"
                      disabled={!horizontalRotationLocked}
                      onPointerDown={(event) => beginHorizontalRotationHold('negative', event)}
                      onPointerUp={() => endHorizontalRotationHold('negative')}
                      onPointerCancel={clearHorizontalRotationHold}
                      onPointerLeave={() => {
                        if (horizontalRotationHoldRef.current.held) clearHorizontalRotationHold();
                      }}
                    >
                      −
                    </button>
                    <button
                      type="button"
                      className={`mv-sdv3d-navigation-axis-label${horizontalRotationLocked ? ' is-active' : ''}`}
                      aria-pressed={horizontalRotationLocked}
                      onClick={() => {
                        clearHorizontalRotationHold();
                        clearVerticalRotationHold();
                        setHorizontalRotationLocked((current) => {
                          const next = !current;
                          if (next) setVerticalRotationLocked(false);
                          return next;
                        });
                      }}
                    >
                      Horizontal
                    </button>
                    <button
                      type="button"
                      aria-label="Rotate horizontally positive"
                      disabled={!horizontalRotationLocked}
                      onPointerDown={(event) => beginHorizontalRotationHold('positive', event)}
                      onPointerUp={() => endHorizontalRotationHold('positive')}
                      onPointerCancel={clearHorizontalRotationHold}
                      onPointerLeave={() => {
                        if (horizontalRotationHoldRef.current.held) clearHorizontalRotationHold();
                      }}
                    >
                      +
                    </button>
                  </div>
                  <div className="mv-sdv3d-navigation-three-column">
                    <button
                      type="button"
                      aria-label="Rotate vertically negative"
                      disabled={!verticalRotationLocked}
                      onPointerDown={(event) => beginVerticalRotationHold('negative', event)}
                      onPointerUp={() => endVerticalRotationHold('negative')}
                      onPointerCancel={clearVerticalRotationHold}
                      onPointerLeave={() => {
                        if (verticalRotationHoldRef.current.held) clearVerticalRotationHold();
                      }}
                    >
                      −
                    </button>
                    <button
                      type="button"
                      className={`mv-sdv3d-navigation-axis-label${verticalRotationLocked ? ' is-active' : ''}`}
                      aria-pressed={verticalRotationLocked}
                      onClick={() => {
                        clearHorizontalRotationHold();
                        clearVerticalRotationHold();
                        setVerticalRotationLocked((current) => {
                          const next = !current;
                          if (next) setHorizontalRotationLocked(false);
                          return next;
                        });
                      }}
                    >
                      Vertical
                    </button>
                    <button
                      type="button"
                      aria-label="Rotate vertically positive"
                      disabled={!verticalRotationLocked}
                      onPointerDown={(event) => beginVerticalRotationHold('positive', event)}
                      onPointerUp={() => endVerticalRotationHold('positive')}
                      onPointerCancel={clearVerticalRotationHold}
                      onPointerLeave={() => {
                        if (verticalRotationHoldRef.current.held) clearVerticalRotationHold();
                      }}
                    >
                      +
                    </button>
                  </div>
                </div>
              </div>
            </div>
            <div className="mv-sdv-info-section mv-sdv-scene-section" style={{ paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div className="mv-sdv-control-subheading mv-sdv-info-heading">
                <span>Scene</span>
                <button
                  type="button"
                  className="mv-sdv-info-badge"
                  onClick={() => setSceneInfoOpen((open) => !open)}
                  aria-label="Scene information"
                  aria-expanded={sceneInfoOpen}
                >
                  i
                </button>
              </div>
              {sceneInfoOpen && (
                <div className="mv-sdv-info-popover" role="note">
                  Mouse wheel zooms the camera. Orbit/pan controls should not change active slices or volume paging.
                  Set Scene stores the current camera, orbit target, zoom level, and scene offset.
                </div>
              )}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                <button
                  type="button"
                  onClick={setSceneView}
                  title="Store the current 3D scene view without changing data or slice state"
                  className="mv-sdv-scene-button"
                  style={{ padding: '5px 8px', cursor: 'pointer' }}
                >
                  Set Scene
                </button>
                <button
                  type="button"
                  onClick={returnSceneView}
                  disabled={!savedSceneView}
                  title="Return to the previously stored 3D scene view"
                  className="mv-sdv-scene-button"
                  style={{
                    color: savedSceneView ? 'var(--mv-text-primary)' : 'var(--mv-text-disabled)',
                    padding: '5px 8px',
                    cursor: savedSceneView ? 'pointer' : 'not-allowed',
                  }}
                >
                  Return
                </button>
                <button
                  type="button"
                  onClick={resetSceneView}
                  title="Reset the 3D scene camera and clear the stored scene view"
                  className="mv-sdv-scene-button"
                  style={{ padding: '5px 8px', cursor: 'pointer' }}
                >
                  Reset Scene
                </button>
              </div>
              <div className="mv-viewer-helper">
                Saved scene: {savedSceneView ? 'set' : 'not set'} · Offset: X {sceneOffsetX.toFixed(1)} · Y {sceneOffsetY.toFixed(1)}
              </div>
            </div>
          </>
        )}

        {activeControlTab === 'planes' && (
          <>
            <div className="mv-sdv3d-visible-planes-section" style={{ borderTop: '1px solid var(--mv-border-normal)', paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div className="mv-sdv-control-subheading">Visible planes</div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <label><input type="checkbox" checked={visiblePlanes.inline} onChange={() => togglePlane('inline')} /> Inline / X {loadingPlanes.inline ? '— loading…' : ''}</label>
                <button
                  className="mv-viewer-compact-button"
                  onClick={() => reloadPlane('inline')}
                  title="Refresh inline/X pane"
                  aria-label="Refresh inline/X pane"
                  style={{ cursor: 'pointer' }}
                >
                  ↻
                </button>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <label><input type="checkbox" checked={visiblePlanes.crossline} onChange={() => togglePlane('crossline')} /> Crossline / Z {loadingPlanes.crossline ? '— loading…' : ''}</label>
                <button
                  className="mv-viewer-compact-button"
                  onClick={() => reloadPlane('crossline')}
                  title="Refresh crossline/Z pane"
                  aria-label="Refresh crossline/Z pane"
                  style={{ cursor: 'pointer' }}
                >
                  ↻
                </button>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <label><input type="checkbox" checked={visiblePlanes.time} onChange={() => togglePlane('time')} /> Time/depth / Y {loadingPlanes.time ? '— loading…' : ''}</label>
                <button
                  className="mv-viewer-compact-button"
                  onClick={() => reloadPlane('time')}
                  title="Refresh time/depth/Y pane"
                  aria-label="Refresh time/depth/Y pane"
                  style={{ cursor: 'pointer' }}
                >
                  ↻
                </button>
              </div>
            </div>
            <div className="mv-sdv3d-slice-movement" style={{ borderTop: '1px solid var(--mv-border-normal)', paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div className="mv-sdv-control-subheading">Slice movement</div>
              <div className="mv-sdv3d-slice-center-row">
                <button
                  className="mv-viewer-compact-button mv-sdv3d-slice-view-button mv-sdv3d-slice-center-button"
                  onClick={centerSlices}
                  style={{ cursor: 'pointer' }}
                >
                  Center
                </button>
              </div>

              <div className="mv-sdv3d-slice-axis-group">
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Inline</span>
                  <input
                    type="number"
                    min={0}
                    max={inlineCount - 1}
                    value={indices.inline}
                    onChange={e => setIndices({ ...indices, inline: clampIndex(parseInt(e.target.value || '0', 10), inlineCount - 1) })}
                    onKeyDown={e => e.stopPropagation()}
                    className="mv-viewer-index-input" style={indexInputStyle}
                  />
                </div>
                <div className="mv-sdv3d-slice-step-row" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <button className="mv-viewer-compact-button mv-sdv3d-slice-view-button" onClick={() => stepInline(-10)} style={{ cursor: 'pointer' }}>-10</button>
                  <button className="mv-viewer-compact-button mv-sdv3d-slice-view-button" onClick={() => stepInline(-1)} style={{ cursor: 'pointer' }}>-1</button>
                  <input className="mv-sdv3d-slice-slider" style={{ flex: 1 }} type="range" min={0} max={inlineCount - 1} value={indices.inline} onChange={e => setIndices({ ...indices, inline: parseInt(e.target.value, 10) })} />
                  <button className="mv-viewer-compact-button mv-sdv3d-slice-view-button" onClick={() => stepInline(1)} style={{ cursor: 'pointer' }}>+1</button>
                  <button className="mv-viewer-compact-button mv-sdv3d-slice-view-button" onClick={() => stepInline(10)} style={{ cursor: 'pointer' }}>+10</button>
                </div>
              </div>

              <div className="mv-sdv3d-slice-axis-group">
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Crossline</span>
                  <input
                    type="number"
                    min={0}
                    max={crosslineCount - 1}
                    value={indices.crossline}
                    onChange={e => setIndices({ ...indices, crossline: clampIndex(parseInt(e.target.value || '0', 10), crosslineCount - 1) })}
                    onKeyDown={e => e.stopPropagation()}
                    className="mv-viewer-index-input" style={indexInputStyle}
                  />
                </div>
                <div className="mv-sdv3d-slice-step-row" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <button className="mv-viewer-compact-button mv-sdv3d-slice-view-button" onClick={() => stepCrossline(-10)} style={{ cursor: 'pointer' }}>-10</button>
                  <button className="mv-viewer-compact-button mv-sdv3d-slice-view-button" onClick={() => stepCrossline(-1)} style={{ cursor: 'pointer' }}>-1</button>
                  <input className="mv-sdv3d-slice-slider" style={{ flex: 1 }} type="range" min={0} max={crosslineCount - 1} value={indices.crossline} onChange={e => setIndices({ ...indices, crossline: parseInt(e.target.value, 10) })} />
                  <button className="mv-viewer-compact-button mv-sdv3d-slice-view-button" onClick={() => stepCrossline(1)} style={{ cursor: 'pointer' }}>+1</button>
                  <button className="mv-viewer-compact-button mv-sdv3d-slice-view-button" onClick={() => stepCrossline(10)} style={{ cursor: 'pointer' }}>+10</button>
                </div>
              </div>

              <div className="mv-sdv3d-slice-axis-group">
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Time/depth</span>
                  <input
                    type="number"
                    min={0}
                    max={timeCount - 1}
                    value={indices.time}
                    onChange={e => {
                      const nextTime = clampIndex(parseInt(e.target.value || '0', 10), timeCount - 1);
                      setIndices({ ...indices, time: nextTime });
                      setCommittedTimeIndex(nextTime);
                    }}
                    onKeyDown={e => e.stopPropagation()}
                    className="mv-viewer-index-input" style={indexInputStyle}
                  />
                </div>
                <div className="mv-sdv3d-slice-step-row" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <button className="mv-viewer-compact-button mv-sdv3d-slice-view-button" onClick={() => stepTime(-10)} style={{ cursor: 'pointer' }}>-10</button>
                  <button className="mv-viewer-compact-button mv-sdv3d-slice-view-button" onClick={() => stepTime(-1)} style={{ cursor: 'pointer' }}>-1</button>
                  <input
                    className="mv-sdv3d-slice-slider"
                    style={{ flex: 1 }}
                    type="range"
                    min={0}
                    max={timeCount - 1}
                    value={indices.time}
                    onChange={e => setIndices({ ...indices, time: parseInt(e.target.value, 10) })}
                    onMouseUp={() => setCommittedTimeIndex(indices.time)}
                    onTouchEnd={() => setCommittedTimeIndex(indices.time)}
                  />
                  <button className="mv-viewer-compact-button mv-sdv3d-slice-view-button" onClick={() => stepTime(1)} style={{ cursor: 'pointer' }}>+1</button>
                  <button className="mv-viewer-compact-button mv-sdv3d-slice-view-button" onClick={() => stepTime(10)} style={{ cursor: 'pointer' }}>+10</button>
                </div>
              </div>
            </div>
          </>
        )}

        {activeControlTab === 'amplitude' && (
          <div className="mv-sdv3d-amplitude-display-section" style={{ borderTop: '1px solid var(--mv-border-normal)', paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div className="mv-sdv-control-subheading">Amplitude / Display</div>
            <div>
              <label>Color Map: </label>
              <select value={colorMap} onChange={e => setColorMap(e.target.value as ColorMapName)} style={{ cursor: 'pointer' }}>
                <option value="seismicTrace">Seismic RWB</option>
                <option value="seismicTraceReverse">Seismic BWR</option>
                <option value="grayscale">Grayscale</option>
                <option value="blackWhiteBlack">Black-White-Black</option>
                <option value="redBlackBlue">Red-Black-Blue</option>
                <option value="brownWhiteBlue">Brown-White-Blue</option>
                <option value="coolwarm">Coolwarm</option>
              </select>
            </div>
            <div>
              <label>Wave Display: </label>
              <select value={waveDisplayMode} onChange={e => setWaveDisplayMode(e.target.value as WaveDisplayMode)} style={{ cursor: 'pointer' }}>
                <option value="full">Full wave</option>
                <option value="peaks">Peaks only</option>
                <option value="troughs">Troughs only</option>
              </select>
            </div>
            <div style={{ fontSize: 12, opacity: 0.7 }}>
              Peaks show positive amplitudes only; troughs show negative amplitudes only. Suppressed polarity is rendered as zero/white.
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr) 48px', alignItems: 'center', gap: 8 }}>
                <label>Amplitude Gain</label>
                <input style={{ width: '100%' }} type="range" min={0.25} max={5} step={0.05} value={amplitudeGain} onChange={e => setAmplitudeGain(parseFloat(e.target.value))} />
                <span style={{ textAlign: 'right' }}>{amplitudeGain.toFixed(2)}×</span>
              </div>
              <div style={{ fontSize: 12, opacity: 0.7 }}>
                Global multiplier applied equally to all panes after clipping.
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr) 48px', alignItems: 'center', gap: 8 }}>
                <label>Clip Percentile</label>
                <input style={{ width: '100%' }} type="range" min={90} max={99.9} step={0.1} value={clipPercentile} onChange={e => setClipPercentile(parseFloat(e.target.value))} />
                <span style={{ textAlign: 'right' }}>{clipPercentile.toFixed(1)}%</span>
              </div>
              <div style={{ fontSize: 12, opacity: 0.7 }}>
                Higher values preserve strong amplitudes; lower values boost weaker events but saturate earlier.
              </div>

              <button
                onClick={() => {
                  setAmplitudeGain(1.0);
                  setClipPercentile(98.5);
                }}
                style={{ background: 'var(--mv-surface-3)', color: 'var(--mv-text-primary)', border: '1px solid var(--mv-border-strong)', padding: '3px 8px', cursor: 'pointer' }}
              >
                Reset gain/clip
              </button>

              <div style={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr) 48px', alignItems: 'center', gap: 8 }}>
                <label>Slice detail</label>
                <input style={{ width: '100%' }} type="range" min={1} max={4} step={0.25} value={textureScale} onChange={e => setTextureScale(parseFloat(e.target.value))} />
                <span style={{ textAlign: 'right' }}>{textureScale === 1 ? 'Native' : `${textureScale.toFixed(2)}×`}</span>
              </div>
              <div style={{ fontSize: 12, opacity: 0.7 }}>
                Higher detail improves still-slice zoom quality. Movement preview stays native for responsiveness.
              </div>
              <button
                onClick={() => setTextureScale(2)}
                style={{ background: 'var(--mv-surface-3)', color: 'var(--mv-text-primary)', border: '1px solid var(--mv-border-strong)', padding: '3px 8px', cursor: 'pointer' }}
              >
                Reset slice detail
              </button>

              <div style={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr) 48px', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <label>Vertical Exag.</label>
                <input style={{ width: '100%' }} type="range" min={0.5} max={4} step={0.1} value={verticalExaggeration} onChange={e => setVerticalExaggeration(parseFloat(e.target.value))} />
                <span style={{ textAlign: 'right' }}>{verticalExaggeration.toFixed(1)}×</span>
              </div>
            </div>
          </div>
        )}

        {activeControlTab === 'volume' && (
          <>
            <div className="mv-sdv3d-volume-stack-section" style={{ borderTop: '1px solid var(--mv-border-normal)', paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div className="mv-sdv-control-subheading">Volume stack</div>

              <label>
                <input
                  type="checkbox"
                  checked={volumeStackEnabled}
                  onChange={() => {
                    setVolumeStackEnabled((v) => {
                      const next = !v;
                      if (next) {
                        setVolumeCenterIndex(
                          volumeBackgroundMode === 'paged' && volumeExtentMode === 'full'
                            ? (
                        volumeRenderDim === 0
                          ? inlineCount - 1
                          : volumeRenderDim === 1
                            ? crosslineCount - 1
                            : timeCount - 1
                      )
                            : volumeRenderDim === 0
                              ? indices.inline
                              : volumeRenderDim === 1
                                ? indices.crossline
                                : indices.time
                        );
                      }
                      return next;
                    });
                  }}
                /> Enable volume stack
              </label>

              <div style={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr)', alignItems: 'center', gap: 8 }}>
                <label>Background</label>
                <select
                  value={volumeBackgroundMode}
                  onChange={(e) => {
                    const nextMode = e.target.value as 'off' | 'whole' | 'paged';
                    setVolumeBackgroundMode(nextMode);

                    if (nextMode === 'paged' && volumeExtentMode === 'full') {
                      // Start paged mode from the opposite side.
                      // Orientation is unchanged; only the starting index changes.
                      setVolumeCenterIndex(
                        volumeRenderDim === 0
                          ? inlineCount - 1
                          : volumeRenderDim === 1
                            ? crosslineCount - 1
                            : timeCount - 1
                      );
                    }
                  }}
                  style={{ background: 'var(--mv-control-bg)', color: 'var(--mv-text-primary)', border: '1px solid var(--mv-border-strong)', padding: '4px 6px' }}
                >
                  <option value="off">Off</option>
                  <option value="whole">Whole cube</option>
                  <option value="paged">Active paging</option>
                    <option value="thickness">Thickness paging</option>
                </select>
              </div>
                {volumeBackgroundMode === 'thickness' && (
                  <div
                    data-role="local-thickness-under-background"
                    style={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr) 48px', alignItems: 'center', gap: 8 }}
                  >
                    <label>Local Thickness</label>
                    <input
                      style={{ width: '100%' }}
                      type="range"
                      min={8}
                      max={256}
                      step={8}
                      value={volumeWindowSize}
                      onChange={(e) => setVolumeWindowSize(parseInt(e.target.value, 10))}
                    />
                    <span style={{ textAlign: 'right' }}>{volumeWindowSize}</span>
                  </div>
                )}

<label>
                <input
                  type="checkbox"
                  checked={volumeWheelScrollEnabled}
                  onChange={() => setVolumeWheelScrollEnabled((v) => !v)}
                /> Mouse wheel scrolls volume
              </label>

              <div style={{ fontSize: 12, opacity: 0.65 }}>
                Use the Volume scroll slider for controlled browsing. Optional mouse-wheel volume scrolling works only while this Volume tab is active; hold Shift for faster slice paging. Hold Option/Alt + wheel for camera zoom while volume-wheel scrolling is enabled.
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr)', alignItems: 'center', gap: 8 }}>
                <label>Direction</label>
                <select
                  value={volumeRenderDim}
                  onChange={(e) => {
                    const nextDim = Number(e.target.value) as 0 | 1 | 2;
                    setVolumeRenderDim(nextDim);
                    setVolumeCenterIndex(getViewerFacingStartIndex(nextDim));
                    setDirectionLoadStatus(null);

                    if (nextDim === 2) {
                      window.requestAnimationFrame(setTimeDirectionCameraView);
                    }
}}
                  style={{ background: 'var(--mv-control-bg)', color: 'var(--mv-text-primary)', border: '1px solid var(--mv-border-strong)', padding: '4px 6px' }}
                >
                  <option value={0}>Inline</option>
                  <option value={1}>Crossline</option>
                  <option value={2}>Time/depth</option>
                </select>
              </div>
                {volumeStackEnabled && (
                  <div
                    data-role="direction-data-inline-panel"
                    style={{
                      marginTop: 10,
                    }}
                  >
                    <div style={{ marginBottom: 8, opacity: 0.85 }}>
                      {directionLoadStatus?.message || 'Direction not loaded'}
                    </div>

                    <div style={{ display: 'flex', gap: 8, marginBottom: directionLoadStatus?.loading ? 8 : 0 }}>
                      <button
                        onClick={() => {
                          if (directionLoadStatus?.loading) {
                            setDirectionPauseRequest((value) => value + 1);
                          } else {
                            setDirectionLoadRequest((value) => value + 1);
                          }
                        }}
                        style={{
                          background: directionLoadStatus?.loading ? '#8a6d1d' : '#2f6fed',
                          color: 'var(--mv-text-primary)',
                          border: 'none',
                          borderRadius: 6,
                          padding: '6px 10px',
                          cursor: 'pointer',
                        }}
                      >
                        {directionLoadStatus?.loading
                          ? 'Pause Load'
                          : directionLoadStatus?.status === 'paused'
                            ? 'Resume Load'
                            : 'Load Direction'}
                      </button>

                      <button
                        onClick={() => setDirectionUnloadRequest((value) => value + 1)}
                        style={{
                          background: 'var(--mv-surface-3)',
                          color: 'var(--mv-text-primary)',
                          border: '1px solid var(--mv-border-strong)',
                          borderRadius: 6,
                          padding: '6px 10px',
                          cursor: 'pointer',
                        }}
                      >
                        Unload
                      </button>
                    </div>

                    {directionLoadStatus?.loading && directionLoadStatus?.total > 0 && (
                      <div style={{ marginTop: 8, height: 6, background: 'var(--mv-surface-3)', borderRadius: 999, overflow: 'hidden' }}>
                        <div
                          style={{
                            width: `${Math.max(0, Math.min(100, (directionLoadStatus.loaded / directionLoadStatus.total) * 100))}%`,
                            height: '100%',
                            background: '#2f6fed',
                          }}
                        />
                      </div>
                    )}
                  </div>
                )}


              <div data-role="load-direction-step-control" style={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr) 48px', alignItems: 'center', gap: 8 }}>
                <label>Page Step</label>
                <input
                  style={{ width: '100%' }}
                  type="range"
                  min={1}
                  max={32}
                  step={1}
                  value={volumeStep}
                  onChange={(e) => setVolumeStep(parseInt(e.target.value, 10))}
                />
                <span style={{ textAlign: 'right' }}>{volumeStep}</span>
              </div>
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    fontSize: 12,
                    opacity: 0.9,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={useStepForPaging}
                    onChange={() => {
                      setUseStepForPaging((value) => {
                        const next = !value;

                        if (next) {
                          const pageStep = Math.max(1, Math.floor(volumeStep || 1));
                          setVolumeCenterIndex((current) => {
                            const snapped = Math.round(current / pageStep) * pageStep;
                            return Math.max(0, Math.min(getVolumeMaxIndex(volumeRenderDim), snapped));
                          });
                        }

                        return next;
                      });
                    }}
                  />
                  Use Step for Paging
                </label>



              <div style={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr)', alignItems: 'center', gap: 8 }}>
                <label>Extent</label>
                <select
                  value={volumeExtentMode}
                  onChange={(e) => {
                    const nextExtent = e.target.value as 'full' | 'local';
                    setVolumeExtentMode(nextExtent);

                    if (nextExtent === 'full' && volumeBackgroundMode === 'paged') {
                      setVolumeCenterIndex(
                        volumeRenderDim === 0
                          ? inlineCount - 1
                          : volumeRenderDim === 1
                            ? crosslineCount - 1
                            : timeCount - 1
                      );
                    }
                  }}
                  style={{ background: 'var(--mv-control-bg)', color: 'var(--mv-text-primary)', border: '1px solid var(--mv-border-strong)', padding: '4px 6px' }}
                >
                  <option value="full">Full cube</option>
                  <option value="local">Local window</option>
                </select>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr)', alignItems: 'center', gap: 8 }}>
                <label>Quality</label>
                <select
                  value={volumeQuality}
                  onChange={(e) => {
                    const nextQuality = e.target.value as 'preview' | 'balanced' | 'high' | 'diagnostic';
                    setVolumeQuality(nextQuality);

                    if (nextQuality === 'preview') {
                      setVolumeOpacity(0.35);
                      setVolumeDensity(1.25);
                      setVolumeThreshold(0.050);
                    } else if (nextQuality === 'balanced') {
                      setVolumeOpacity(0.55);
                      setVolumeDensity(2.00);
                      setVolumeThreshold(0.035);
                    } else if (nextQuality === 'high') {
                      setVolumeOpacity(0.75);
                      setVolumeDensity(2.75);
                      setVolumeThreshold(0.020);
                    } else {
                      setVolumeOpacity(1.00);
                      setVolumeDensity(4.00);
                      setVolumeThreshold(0.000);
                    }
                  }}
                  style={{ background: 'var(--mv-control-bg)', color: 'var(--mv-text-primary)', border: '1px solid var(--mv-border-strong)', padding: '4px 6px' }}
                >
                  <option value="preview">Preview</option>
                  <option value="balanced">Balanced</option>
                  <option value="high">High</option>
                  <option value="diagnostic">Diagnostic</option>
                </select>
              </div>
<div style={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr) 48px', alignItems: 'center', gap: 8 }}>
                <label>Volume scroll</label>
                <input
                  style={{ width: '100%' }}
                  type="range"
                  min={0}
                  max={Math.max(0, volumeRenderDim === 0 ? inlineCount - 1 : volumeRenderDim === 1 ? crosslineCount - 1 : timeCount - 1)}
                  step={1}
                  value={volumeCenterIndex}
                  step={getVolumePageStepSize()}
                  onChange={(e) => setVolumeCenterIndex(clampVolumeIndex(parseInt(e.target.value, 10)))}
                />
                <span style={{ textAlign: 'right' }}>{volumeCenterIndex}</span>
              </div>



              <div style={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr) 48px', alignItems: 'center', gap: 8 }}>
                <label>Opacity</label>
                <input
                  style={{ width: '100%' }}
                  type="range"
                  min={0.01}
                  max={1}
                  step={0.01}
                  value={volumeOpacity}
                  onChange={(e) => setVolumeOpacity(parseFloat(e.target.value))}
                />
                <span style={{ textAlign: 'right' }}>{volumeOpacity.toFixed(2)}</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr) 48px', alignItems: 'center', gap: 8 }}>
                <label>Density</label>
                <input
                  style={{ width: '100%' }}
                  type="range"
                  min={0.1}
                  max={8}
                  step={0.05}
                  value={volumeDensity}
                  onChange={(e) => setVolumeDensity(parseFloat(e.target.value))}
                />
                <span style={{ textAlign: 'right' }}>{volumeDensity.toFixed(2)}×</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '100px minmax(0, 1fr) 48px', alignItems: 'center', gap: 8 }}>
                <label>Threshold</label>
                <input
                  style={{ width: '100%' }}
                  type="range"
                  min={0}
                  max={0.35}
                  step={0.005}
                  value={volumeThreshold}
                  onChange={(e) => setVolumeThreshold(parseFloat(e.target.value))}
                />
                <span style={{ textAlign: 'right' }}>{volumeThreshold.toFixed(3)}</span>
              </div>

              <button
                type="button"
                onClick={resetCubeControls}
                style={{
                  marginTop: 12,
                  width: '100%',
                  padding: '7px 10px',
                  background: 'var(--mv-surface-2)',
                  color: 'var(--mv-text-primary)',
                  border: '1px solid var(--mv-border-strong)',
                  borderRadius: 4,
                  cursor: 'pointer',
                  fontSize: 12,
                }}
              >
                Reset cube
              </button>

              <div style={{ fontSize: 12, opacity: 0.65 }}>
                Background controls volume context: Off shows only the active slice, Whole cube keeps the sampled cube fixed, Active paging shows only pages ahead of the active slice.</div>
            </div>
          </>
        )}

        {activeControlTab === 'performance' && (
          <>
            <div className="mv-sdv3d-performance-section" style={{ borderTop: '1px solid var(--mv-border-normal)', paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div className="mv-sdv-control-subheading">Performance / System</div>

              <label>
                <input
                  type="checkbox"
                  checked={fastPreviewWhileMoving}
                  onChange={() => setFastPreviewWhileMoving((v) => !v)}
                /> Fast preview while moving
              </label>
              <div style={{ fontSize: 12, opacity: 0.65 }}>
                Uses native texture resolution while slices are moving, then returns to the selected quality when movement settles.
              </div>

              <label>
                <input
                  type="checkbox"
                  checked={livePreviewWhileDragging}
                  onChange={() => setLivePreviewWhileDragging((v) => !v)}
                /> Live amplitude preview while dragging panes
              </label>
              <div style={{ fontSize: 12, opacity: 0.65 }}>
                While Shift-dragging a pane, updates that pane’s amplitude texture during movement using a 100 ms preview cadence and native texture resolution.
              </div>

              <div>
                <label>Time/depth refresh: </label>
                <select
                  value={timeRefreshMode}
                  onChange={e => {
                    const nextMode = e.target.value as TimeRefreshMode;
                    setTimeRefreshMode(nextMode);
                    if (nextMode === 'onRelease') setCommittedTimeIndex(indices.time);
                  }}
                  style={{ cursor: 'pointer' }}
                >
                  <option value="immediate">Immediate</option>
                  <option value="debounced">Debounced</option>
                  <option value="onRelease">On release only</option>
                </select>
              </div>
              <div style={{ fontSize: 12, opacity: 0.65 }}>
                Debounced is safest. On release only delays expensive time/depth texture refresh until slider/pane movement is released.
              </div>

              <div>
                <label>Slice cache size: </label>
                <select
                  value={cacheSize}
                  onChange={e => setCacheSize(parseInt(e.target.value, 10))}
                  style={{ cursor: 'pointer' }}
                >
                  <option value={16}>16 slices</option>
                  <option value={32}>32 slices</option>
                  <option value={64}>64 slices</option>
                  <option value={128}>128 slices</option>
                </select>
              </div>
              <div style={{ fontSize: 12, opacity: 0.65 }}>
                Frontend cached slices currently stored: {sliceCache.size} / {cacheSize}
              </div>
              <div style={{ fontSize: 12, opacity: 0.65 }}>
                Backend cache: {backendCacheInfo ? `${backendCacheInfo.entries} entries · ${(backendCacheInfo.bytes / 1048576).toFixed(1)} MB / ${(backendCacheInfo.max_bytes / 1048576).toFixed(0)} MB` : 'not available'}
              </div>
              <button
                onClick={refreshBackendCacheInfo}
                style={{ background: 'var(--mv-surface-3)', color: 'var(--mv-text-primary)', border: '1px solid var(--mv-border-strong)', padding: '3px 8px', cursor: 'pointer' }}
              >
                Refresh backend cache info
              </button>
              <div style={{ fontSize: 12, opacity: 0.65 }}>
                Backend cache info auto-refreshes every 5 seconds while this tab is open.
              </div>

              <div style={{ fontSize: 12, opacity: 0.65 }}>
                Loading state — Inline: {loadingPlanes.inline ? 'loading' : 'idle'} · Crossline: {loadingPlanes.crossline ? 'loading' : 'idle'} · Time: {loadingPlanes.time ? 'loading' : 'idle'}
              </div>
              <div style={{ fontSize: 12, opacity: 0.65 }}>
                Drag preview — {isLivePreviewing ? `active on ${draggingAxis}` : 'idle'}
              </div>
              <button
                onClick={clearSliceCacheAndRefresh}
                style={{ background: 'var(--mv-surface-3)', color: 'var(--mv-text-primary)', border: '1px solid var(--mv-border-strong)', padding: '4px 8px', cursor: 'pointer' }}
              >
                Clear frontend + backend slice cache
              </button>
            </div>
          </>
        )}
      </div>

      {sceneOverlaysModalOpen && (
        <div className="mv-modal-backdrop mv-sdv3d-scene-overlays-modal-backdrop" role="presentation">
          <section
            ref={sceneOverlaysModalRef}
            className="mv-modal mv-sdv3d-scene-overlays-modal"
            role="dialog"
            aria-modal="false"
            aria-labelledby="sdv3d-scene-overlays-modal-title"
            style={{
              transform: `translate3d(${sceneOverlaysModalOffset.x}px, ${sceneOverlaysModalOffset.y}px, 0)`,
            }}
          >
            <header
              className="mv-modal__header mv-sdv3d-scene-overlays-modal-header"
              onPointerDown={beginSceneOverlaysModalDrag}
              onPointerMove={moveSceneOverlaysModalDrag}
              onPointerUp={endSceneOverlaysModalDrag}
              onPointerCancel={endSceneOverlaysModalDrag}
              onLostPointerCapture={loseSceneOverlaysModalPointerCapture}
            >
              <div>
                <h2 id="sdv3d-scene-overlays-modal-title">Manage Scene Overlays</h2>
              </div>
              <button
                type="button"
                className="mv-button mv-button--compact"
                aria-label="Close Scene Overlays manager"
                onClick={cancelSceneOverlaysModal}
              >
                ×
              </button>
            </header>

            <div className="mv-sdv3d-scene-overlays-modal-body">
              <aside className="mv-sdv3d-scene-overlays-modal-rail" aria-label="Scene Overlay layers">
                <div className="mv-sdv3d-scene-overlays-modal-rail-heading">Scene Overlays</div>
                <div className="mv-sdv3d-scene-overlays-modal-nav">
                  {([
                    ['grid', 'Horizontal Grid'],
                    ['bounds', 'Bounding Box'],
                    ['axes', 'X/Y/Z Axis Lines'],
                    ['labels', 'Axis Labels'],
                    ['compass', 'Compass'],
                  ] as const).map(([key, label]) => (
                    <button
                      type="button"
                      key={key}
                      className={selectedSceneOverlayLayer === key ? 'is-current' : ''}
                      onClick={() => setSelectedSceneOverlayLayer(key)}
                    >
                      <span>{label}</span>
                    </button>
                  ))}
                </div>
              </aside>

              <section className="mv-sdv3d-scene-overlays-modal-editor">
                <header className="mv-sdv3d-scene-overlays-modal-editor-header">
                  <div>
                    <h3>
                      {{
                        grid: 'Horizontal Grid',
                        bounds: 'Bounding Box',
                        axes: 'X/Y/Z Axis Lines',
                        labels: 'Axis Labels',
                        compass: 'Compass',
                      }[selectedSceneOverlayLayer]}
                    </h3>
                    <p>Appearance and display settings</p>
                  </div>
                </header>

                <div className="mv-sdv3d-scene-overlays-modal-content">
                  <div className="mv-sdv3d-scene-overlays-property-card">
                    <h4>Display</h4>
                    <label className="mv-sdv3d-scene-overlays-check-row">
                      <input
                        type="checkbox"
                        checked={sceneOverlayDraftVisibility[selectedSceneOverlayLayer]}
                        onChange={(event) => {
                          const checked = event.target.checked;
                          setSceneOverlayDraftVisibility((current) => ({
                            ...current,
                            [selectedSceneOverlayLayer]: checked,
                          }));
                        }}
                      />
                      <span>Show layer</span>
                    </label>
                  </div>

                  {selectedSceneOverlayLayer === 'grid' && (
                    <div className="mv-sdv3d-scene-overlays-property-card">
                      <h4>Grid Lines</h4>
                      <div className="mv-sdv3d-scene-overlays-property-grid">
                        <label className="mv-sdv3d-scene-overlays-field">
                          <span>Grid color</span>
                          <input
                            className="mv-modal-swatch"
                            type="color"
                            value={sceneOverlayDraftAppearance.grid.color ?? canvasGridColor}
                            onChange={(event) => {
                              const color = event.target.value;
                              setSceneOverlayDraftAppearance((current) => ({
                                ...current,
                                grid: { ...current.grid, color },
                              }));
                            }}
                          />
                        </label>
                        <label className="mv-sdv3d-scene-overlays-field mv-sdv3d-scene-overlays-range-field">
                          <span>Opacity</span>
                          <span className="mv-sdv3d-scene-overlays-range-control">
                            <input
                              className="mv-modal-slider"
                              type="range"
                              min="0"
                              max="1"
                              step="0.05"
                              value={sceneOverlayDraftAppearance.grid.opacity}
                              onChange={(event) => {
                                const opacity = Number(event.target.value);
                                setSceneOverlayDraftAppearance((current) => ({
                                  ...current,
                                  grid: { ...current.grid, opacity },
                                }));
                              }}
                            />
                            <input
                              className="mv-modal-number--compact"
                              type="number"
                              min="0"
                              max="1"
                              step="0.05"
                              value={sceneOverlayDraftAppearance.grid.opacity}
                              onChange={(event) => {
                                const opacity = Math.max(0, Math.min(1, Number(event.target.value)));
                                setSceneOverlayDraftAppearance((current) => ({
                                  ...current,
                                  grid: { ...current.grid, opacity },
                                }));
                              }}
                            />
                          </span>
                        </label>
                      </div>
                    </div>
                  )}

                  {selectedSceneOverlayLayer === 'bounds' && (
                    <div className="mv-sdv3d-scene-overlays-property-card">
                      <h4>Lines</h4>
                      <div className="mv-sdv3d-scene-overlays-property-grid">
                        <label className="mv-sdv3d-scene-overlays-field">
                          <span>Line color</span>
                          <input
                            className="mv-modal-swatch"
                            type="color"
                            value={sceneOverlayDraftAppearance.bounds.color ?? canvasBoundingBoxColor}
                            onChange={(event) => {
                              const color = event.target.value;
                              setSceneOverlayDraftAppearance((current) => ({
                                ...current,
                                bounds: { ...current.bounds, color },
                              }));
                            }}
                          />
                        </label>
                        <label className="mv-sdv3d-scene-overlays-field mv-sdv3d-scene-overlays-range-field">
                          <span>Opacity</span>
                          <span className="mv-sdv3d-scene-overlays-range-control">
                            <input
                              className="mv-modal-slider"
                              type="range"
                              min="0"
                              max="1"
                              step="0.05"
                              value={sceneOverlayDraftAppearance.bounds.opacity ?? (canvasShadeAdaptive ? 0.72 : 0.35)}
                              onChange={(event) => {
                                const opacity = Number(event.target.value);
                                setSceneOverlayDraftAppearance((current) => ({
                                  ...current,
                                  bounds: { ...current.bounds, opacity },
                                }));
                              }}
                            />
                            <input
                              className="mv-modal-number--compact"
                              type="number"
                              min="0"
                              max="1"
                              step="0.05"
                              value={sceneOverlayDraftAppearance.bounds.opacity ?? (canvasShadeAdaptive ? 0.72 : 0.35)}
                              onChange={(event) => {
                                const opacity = Math.max(0, Math.min(1, Number(event.target.value)));
                                setSceneOverlayDraftAppearance((current) => ({
                                  ...current,
                                  bounds: { ...current.bounds, opacity },
                                }));
                              }}
                            />
                          </span>
                        </label>
                      </div>
                    </div>
                  )}

                  {selectedSceneOverlayLayer === 'axes' && (
                    <div className="mv-sdv3d-scene-overlays-property-card">
                      <h4>Axis Lines</h4>
                      <div className="mv-sdv3d-scene-overlays-property-grid">
                        <label className="mv-sdv3d-scene-overlays-field mv-sdv3d-scene-overlays-range-field">
                          <span>Axis size</span>
                          <span className="mv-sdv3d-scene-overlays-range-control">
                            <input
                              className="mv-modal-slider"
                              type="range"
                              min="0.5"
                              max="2"
                              step="0.05"
                              value={sceneOverlayDraftAppearance.axes.scale}
                              onChange={(event) => {
                                const scale = Number(event.target.value);
                                setSceneOverlayDraftAppearance((current) => ({
                                  ...current,
                                  axes: { scale },
                                }));
                              }}
                            />
                            <input
                              className="mv-modal-number--compact"
                              type="number"
                              min="0.5"
                              max="2"
                              step="0.05"
                              value={sceneOverlayDraftAppearance.axes.scale}
                              onChange={(event) => {
                                const scale = Math.max(0.5, Math.min(2, Number(event.target.value)));
                                setSceneOverlayDraftAppearance((current) => ({
                                  ...current,
                                  axes: { scale },
                                }));
                              }}
                            />
                          </span>
                        </label>
                      </div>
                    </div>
                  )}

                  {selectedSceneOverlayLayer === 'labels' && (
                    <div className="mv-sdv3d-scene-overlays-property-card">
                      <h4>Labels</h4>
                      <div className="mv-sdv3d-scene-overlays-property-grid">
                        <label className="mv-sdv3d-scene-overlays-field">
                          <span>Text color</span>
                          <input
                            className="mv-modal-swatch"
                            type="color"
                            value={sceneOverlayDraftAppearance.labels.color ?? canvasEnvironmentPalette.axisTextColor}
                            onChange={(event) => {
                              const color = event.target.value;
                              setSceneOverlayDraftAppearance((current) => ({
                                ...current,
                                labels: { ...current.labels, color },
                              }));
                            }}
                          />
                        </label>
                        <label className="mv-sdv3d-scene-overlays-field mv-sdv3d-scene-overlays-range-field">
                          <span>Label size</span>
                          <span className="mv-sdv3d-scene-overlays-range-control">
                            <input
                              className="mv-modal-slider"
                              type="range"
                              min="0.5"
                              max="2"
                              step="0.05"
                              value={sceneOverlayDraftAppearance.labels.sizeScale}
                              onChange={(event) => {
                                const sizeScale = Number(event.target.value);
                                setSceneOverlayDraftAppearance((current) => ({
                                  ...current,
                                  labels: { ...current.labels, sizeScale },
                                }));
                              }}
                            />
                            <input
                              className="mv-modal-number--compact"
                              type="number"
                              min="0.5"
                              max="2"
                              step="0.05"
                              value={sceneOverlayDraftAppearance.labels.sizeScale}
                              onChange={(event) => {
                                const sizeScale = Math.max(0.5, Math.min(2, Number(event.target.value)));
                                setSceneOverlayDraftAppearance((current) => ({
                                  ...current,
                                  labels: { ...current.labels, sizeScale },
                                }));
                              }}
                            />
                          </span>
                        </label>
                        <label className="mv-sdv3d-scene-overlays-field mv-sdv3d-scene-overlays-range-field">
                          <span>Opacity</span>
                          <span className="mv-sdv3d-scene-overlays-range-control">
                            <input
                              className="mv-modal-slider"
                              type="range"
                              min="0"
                              max="1"
                              step="0.05"
                              value={sceneOverlayDraftAppearance.labels.opacityScale}
                              onChange={(event) => {
                                const opacityScale = Number(event.target.value);
                                setSceneOverlayDraftAppearance((current) => ({
                                  ...current,
                                  labels: { ...current.labels, opacityScale },
                                }));
                              }}
                            />
                            <input
                              className="mv-modal-number--compact"
                              type="number"
                              min="0"
                              max="1"
                              step="0.05"
                              value={sceneOverlayDraftAppearance.labels.opacityScale}
                              onChange={(event) => {
                                const opacityScale = Math.max(0, Math.min(1, Number(event.target.value)));
                                setSceneOverlayDraftAppearance((current) => ({
                                  ...current,
                                  labels: { ...current.labels, opacityScale },
                                }));
                              }}
                            />
                          </span>
                        </label>
                      </div>
                    </div>
                  )}

                  {selectedSceneOverlayLayer === 'compass' && (
                    <div className="mv-sdv3d-scene-overlays-property-card">
                      <h4>Compass</h4>
                      <div className="mv-sdv3d-scene-overlays-property-grid">
                        <label className="mv-sdv3d-scene-overlays-field mv-sdv3d-scene-overlays-range-field">
                          <span>Size</span>
                          <span className="mv-sdv3d-scene-overlays-range-control">
                            <input
                              className="mv-modal-slider"
                              type="range"
                              min="0.75"
                              max="1.5"
                              step="0.05"
                              value={sceneOverlayDraftAppearance.compass.sizeScale}
                              onChange={(event) => {
                                const sizeScale = Number(event.target.value);
                                setSceneOverlayDraftAppearance((current) => ({
                                  ...current,
                                  compass: { ...current.compass, sizeScale },
                                }));
                              }}
                            />
                            <input
                              className="mv-modal-number--compact"
                              type="number"
                              min="0.75"
                              max="1.5"
                              step="0.05"
                              value={sceneOverlayDraftAppearance.compass.sizeScale}
                              onChange={(event) => {
                                const sizeScale = Math.max(0.75, Math.min(1.5, Number(event.target.value)));
                                setSceneOverlayDraftAppearance((current) => ({
                                  ...current,
                                  compass: { ...current.compass, sizeScale },
                                }));
                              }}
                            />
                          </span>
                        </label>
                        <label className="mv-sdv3d-scene-overlays-field mv-sdv3d-scene-overlays-range-field">
                          <span>Opacity</span>
                          <span className="mv-sdv3d-scene-overlays-range-control">
                            <input
                              className="mv-modal-slider"
                              type="range"
                              min="0"
                              max="1"
                              step="0.05"
                              value={sceneOverlayDraftAppearance.compass.opacity}
                              onChange={(event) => {
                                const opacity = Number(event.target.value);
                                setSceneOverlayDraftAppearance((current) => ({
                                  ...current,
                                  compass: { ...current.compass, opacity },
                                }));
                              }}
                            />
                            <input
                              className="mv-modal-number--compact"
                              type="number"
                              min="0"
                              max="1"
                              step="0.05"
                              value={sceneOverlayDraftAppearance.compass.opacity}
                              onChange={(event) => {
                                const opacity = Math.max(0, Math.min(1, Number(event.target.value)));
                                setSceneOverlayDraftAppearance((current) => ({
                                  ...current,
                                  compass: { ...current.compass, opacity },
                                }));
                              }}
                            />
                          </span>
                        </label>
                      </div>
                    </div>
                  )}
                </div>
              </section>
            </div>

            <footer className="mv-modal__footer mv-sdv3d-scene-overlays-modal-footer">
              <div className="mv-sdv3d-scene-overlays-modal-footer-left">
                <button
                  type="button"
                  className="mv-button mv-button--secondary"
                  onClick={resetSelectedSceneOverlayLayer}
                >
                  Reset Layer
                </button>
              </div>
              <div className="mv-sdv3d-scene-overlays-modal-footer-right">
                <button
                  type="button"
                  className="mv-button mv-button--secondary"
                  onClick={cancelSceneOverlaysModal}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="mv-button mv-button--accent"
                  onClick={applySceneOverlaysModal}
                >
                  Apply
                </button>
              </div>
            </footer>
          </section>
        </div>
      )}

      {infoCollapsed && (
        <button
          onClick={() => setInfoCollapsed(false)}
          style={{
            position: 'absolute',
            top: 18,
            right: 0,
            zIndex: 10,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            minHeight: 136,
            padding: '10px 6px',
            background: 'var(--mv-surface-1)',
            color: 'var(--mv-text-primary)',
            border: '1px solid var(--mv-border-strong)',
            borderRight: 'none',
            borderRadius: '8px 0 0 8px',
            cursor: 'pointer',
            boxSizing: 'border-box',
          }}
          title="Expand information panel"
          aria-label="Expand information panel"
        >
          <span style={{ fontSize: 16, lineHeight: 1 }}>◀</span>
          <span
            style={{
              writingMode: 'vertical-rl',
              transform: 'rotate(180deg)',
              letterSpacing: 1,
              lineHeight: 1,
            }}
          >
            Info
          </span>
        </button>
      )}

      {menuCollapsed && (
        <button
          onClick={() => setMenuCollapsed(false)}
          style={{
            position: 'absolute',
            top: 18,
            left: 0,
            zIndex: 13,
            writingMode: 'vertical-rl',
            transform: 'rotate(180deg)',
            background: 'var(--mv-surface-1)',
            color: 'var(--mv-text-primary)',
            border: '1px solid var(--mv-border-strong)',
            borderLeft: 'none',
            borderRadius: '0 8px 8px 0',
            padding: '10px 6px',
            cursor: 'pointer',
            letterSpacing: 1,
          }}
          title="Expand controls"
        >
          Controls ▶
        </button>
      )}
    </div>
  );
};
