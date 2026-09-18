import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { fetchSlice } from '../services/zarrService';

type ColorMapName =
  | 'seismicTrace'
  | 'seismicTraceReverse'
  | 'grayscale'
  | 'blackWhiteBlack'
  | 'redBlackBlue'
  | 'brownWhiteBlue'
  | 'coolwarm';

type WaveDisplayMode = 'full' | 'peaks' | 'troughs';
type VolumeExtentMode = 'full' | 'local';
type VolumeQuality = 'preview' | 'balanced' | 'high' | 'diagnostic';

type VolumeCacheStatus = {
  loading: boolean;
  message: string;
};

type VolumeStackRendererProps = {
  zarrPath: string;
  dim: 0 | 1 | 2;
  centerIndex: number;
  maxIndex: number;
  windowSize: number;
  step: number;
  extentMode: VolumeExtentMode;
  quality: VolumeQuality;
  showBackground: boolean;
  opacity: number;
  density: number;
  threshold: number;
  amplitudeGain: number;
  clipPercentile: number;
  colorMap: ColorMapName;
  waveDisplayMode: WaveDisplayMode;
  worldSize: { x: number; y: number; z: number };
  onCacheStatus?: (status: VolumeCacheStatus | null) => void;
};

type LoadedStackSlice = {
  index: number;
  texture: THREE.DataTexture;
  active: boolean;
};

type TextureCacheEntry = {
  texture: THREE.DataTexture;
  lastUsed: number;
};

const MAX_TEXTURE_CACHE_ENTRIES = 1024;
const ACTIVE_BLOCK_SIZE = 64;
const ACTIVE_BLOCK_RADIUS = 1;
const BACKGROUND_BATCH_SIZE = 4;
const ACTIVE_BLOCK_BATCH_SIZE = 3;

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function clamp255(value: number): number {
  return Math.max(0, Math.min(255, Math.round(value)));
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function idleTick(): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, 0);
  });
}

function mixRgb(
  a: [number, number, number],
  b: [number, number, number],
  t: number
): [number, number, number] {
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
  positiveColor: [number, number, number]
): [number, number, number] {
  if (norm >= 0) return mixRgb(centerColor, positiveColor, clamp01(norm));
  return mixRgb(centerColor, negativeColor, clamp01(-norm));
}

function colorForNorm(norm: number, colorMap: ColorMapName): [number, number, number] {
  switch (colorMap) {
    case 'grayscale': {
      const gray = Math.round(clamp01(0.5 + 0.5 * norm) * 255);
      return [gray, gray, gray];
    }
    case 'blackWhiteBlack': {
      const gray = Math.round((1 - clamp01(Math.abs(norm))) * 255);
      return [gray, gray, gray];
    }
    case 'seismicTraceReverse':
      return divergingColor(norm, [255, 0, 0], [255, 255, 255], [0, 0, 255]);
    case 'redBlackBlue':
      return divergingColor(norm, [0, 90, 255], [0, 0, 0], [255, 60, 60]);
    case 'brownWhiteBlue':
      return divergingColor(norm, [50, 90, 210], [255, 255, 255], [150, 95, 45]);
    case 'coolwarm':
      return divergingColor(norm, [59, 76, 192], [245, 245, 245], [180, 4, 38]);
    case 'seismicTrace':
    default:
      return divergingColor(norm, [0, 0, 255], [255, 255, 255], [255, 0, 0]);
  }
}

function estimateClipAbs(data: Float32Array, clipPercentile: number): number {
  const n = data.length;
  if (n === 0) return 1;

  const maxSamples = 50000;
  const stride = Math.max(1, Math.floor(n / maxSamples));
  const samples: number[] = [];

  for (let i = 0; i < n; i += stride) {
    const value = Math.abs(data[i]);
    if (Number.isFinite(value)) samples.push(value);
  }

  if (samples.length === 0) return 1;

  samples.sort((a, b) => a - b);

  const pct = Math.max(50, Math.min(99.99, clipPercentile));
  const index = Math.min(
    samples.length - 1,
    Math.max(0, Math.floor((pct / 100) * (samples.length - 1)))
  );

  const clip = samples[index];
  return clip > 0 && Number.isFinite(clip) ? clip : samples[samples.length - 1] || 1;
}

function getSourceIndex(
  texX: number,
  texY: number,
  axis0Count: number,
  axis1Count: number,
  flipAxis0: boolean,
  flipAxis1: boolean
): number {
  const sourceAxis0 = flipAxis0 ? axis0Count - 1 - texX : texX;
  const sourceAxis1 = flipAxis1 ? axis1Count - 1 - texY : texY;
  return sourceAxis0 * axis1Count + sourceAxis1;
}

function buildTextureFromSlice(
  data: Float32Array,
  shape: number[],
  dim: 0 | 1 | 2,
  amplitudeGain: number,
  clipPercentile: number,
  density: number,
  threshold: number,
  colorMap: ColorMapName,
  waveDisplayMode: WaveDisplayMode,
  opaqueMode: boolean
): THREE.DataTexture {
  const axis0Count = shape[0] ?? 1;
  const axis1Count = shape[1] ?? 1;
  const width = axis0Count;
  const height = axis1Count;
  const rgba = new Uint8Array(width * height * 4);

  const amplitudeClip = estimateClipAbs(data, clipPercentile);
  const safeClip = amplitudeClip > 0 ? amplitudeClip : 1;

  const flipAxis0 = dim === 0;
  const flipAxis1 = dim === 2;

  for (let texY = 0; texY < height; texY += 1) {
    for (let texX = 0; texX < width; texX += 1) {
      const src = getSourceIndex(texX, texY, axis0Count, axis1Count, flipAxis0, flipAxis1);
      let norm = Math.max(-1, Math.min(1, (data[src] / safeClip) * amplitudeGain));

      if (waveDisplayMode === 'peaks' && norm < 0) norm = 0;
      if (waveDisplayMode === 'troughs' && norm > 0) norm = 0;

      const absNorm = Math.abs(norm);
      const dst = (texY * width + texX) * 4;

      if (!opaqueMode && absNorm <= threshold) {
        rgba[dst] = 0;
        rgba[dst + 1] = 0;
        rgba[dst + 2] = 0;
        rgba[dst + 3] = 0;
        continue;
      }

      const rgb = colorForNorm(norm, colorMap);

      rgba[dst] = rgb[0];
      rgba[dst + 1] = rgb[1];
      rgba[dst + 2] = rgb[2];

      if (opaqueMode) {
        rgba[dst + 3] = 255;
      } else {
        const alphaNorm = threshold >= 1
          ? 0
          : (absNorm - threshold) / Math.max(0.0001, 1 - threshold);

        const visibleAlpha = alphaNorm <= 0
          ? 0
          : Math.max(0.08, Math.sqrt(clamp01(alphaNorm)) * density);

        rgba[dst + 3] = clamp255(255 * clamp01(visibleAlpha));
      }
    }
  }

  const texture = new THREE.DataTexture(
    rgba,
    width,
    height,
    THREE.RGBAFormat,
    THREE.UnsignedByteType
  );

  texture.needsUpdate = true;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.flipY = false;

  return texture;
}

function targetSliceCountForQuality(quality: VolumeQuality): number {
  if (quality === 'preview') return 16;
  if (quality === 'balanced') return 80;
  if (quality === 'high') return 140;
  return 24;
}

function makeTextureCacheKey(
  displaySignature: string,
  index: number,
  opaqueMode: boolean
): string {
  return `${displaySignature}|index=${index}|opaque=${opaqueMode ? 1 : 0}`;
}

function buildBlockIndexes(activeIndex: number, maxIndex: number): number[] {
  const currentBlock = Math.floor(activeIndex / ACTIVE_BLOCK_SIZE);
  const startBlock = Math.max(0, currentBlock - ACTIVE_BLOCK_RADIUS);
  const endBlock = Math.floor(maxIndex / ACTIVE_BLOCK_SIZE);
  const lastBlock = Math.min(endBlock, currentBlock + ACTIVE_BLOCK_RADIUS);
  const indexes: number[] = [];

  for (let block = startBlock; block <= lastBlock; block += 1) {
    const start = block * ACTIVE_BLOCK_SIZE;
    const end = Math.min(maxIndex, start + ACTIVE_BLOCK_SIZE - 1);

    for (let index = start; index <= end; index += 1) {
      indexes.push(index);
    }
  }

  return indexes;
}

function getBlockRange(activeIndex: number, maxIndex: number): { start: number; end: number } {
  const currentBlock = Math.floor(activeIndex / ACTIVE_BLOCK_SIZE);
  const startBlock = Math.max(0, currentBlock - ACTIVE_BLOCK_RADIUS);
  const endBlock = Math.floor(maxIndex / ACTIVE_BLOCK_SIZE);
  const lastBlock = Math.min(endBlock, currentBlock + ACTIVE_BLOCK_RADIUS);

  return {
    start: startBlock * ACTIVE_BLOCK_SIZE,
    end: Math.min(maxIndex, (lastBlock + 1) * ACTIVE_BLOCK_SIZE - 1),
  };
}

function orderIndexesByDistance(indexes: number[], activeIndex: number): number[] {
  return [...indexes].sort((a, b) => {
    const da = Math.abs(a - activeIndex);
    const db = Math.abs(b - activeIndex);
    if (da !== db) return da - db;
    return a - b;
  });
}

function getPlaneTransform(
  dim: 0 | 1 | 2,
  index: number,
  maxIndex: number,
  worldSize: { x: number; y: number; z: number }
): {
  position: [number, number, number];
  rotation: [number, number, number];
  planeSize: [number, number];
} {
  const t = maxIndex > 0 ? index / maxIndex - 0.5 : 0;

  if (dim === 0) {
    return {
      position: [t * worldSize.x, 0, 0],
      rotation: [0, Math.PI / 2, 0],
      planeSize: [worldSize.z, worldSize.y],
    };
  }

  if (dim === 1) {
    return {
      position: [0, 0, t * worldSize.z],
      rotation: [0, 0, 0],
      planeSize: [worldSize.x, worldSize.y],
    };
  }

  return {
    position: [0, t * worldSize.y, 0],
    rotation: [-Math.PI / 2, 0, 0],
    planeSize: [worldSize.x, worldSize.z],
  };
}

export default function VolumeStackRenderer({
  zarrPath,
  dim,
  centerIndex,
  maxIndex,
  windowSize,
  step,
  extentMode,
  quality,
  showBackground,
  opacity,
  density,
  threshold,
  amplitudeGain,
  clipPercentile,
  colorMap,
  waveDisplayMode,
  worldSize,
  onCacheStatus,
}: VolumeStackRendererProps) {
  const [baseSlices, setBaseSlices] = useState<LoadedStackSlice[]>([]);
  const [activeSlice, setActiveSlice] = useState<LoadedStackSlice | null>(null);

  const textureCacheRef = useRef<Map<string, TextureCacheEntry>>(new Map());
  const lastDisplaySignatureRef = useRef<string>('');
  const requestVersionRef = useRef(0);
  const activeBlockSignatureRef = useRef<string>('');

  const displaySettingsSignature = useMemo(() => {
    return [
      zarrPath,
      amplitudeGain.toFixed(4),
      clipPercentile.toFixed(3),
      density.toFixed(3),
      threshold.toFixed(4),
      colorMap,
      waveDisplayMode,
    ].join('|');
  }, [
    amplitudeGain,
    clipPercentile,
    colorMap,
    density,
    threshold,
    waveDisplayMode,
    zarrPath,
  ]);

  const displaySignature = useMemo(() => {
    return [displaySettingsSignature, `dim=${dim}`].join('|');
  }, [dim, displaySettingsSignature]);

  useEffect(() => {
    if (
      lastDisplaySignatureRef.current &&
      lastDisplaySignatureRef.current !== displaySettingsSignature
    ) {
      textureCacheRef.current.forEach((entry) => entry.texture.dispose());
      textureCacheRef.current.clear();
      setBaseSlices([]);
      setActiveSlice(null);
    }

    lastDisplaySignatureRef.current = displaySettingsSignature;
  }, [displaySettingsSignature]);

  const activeIndex = useMemo(() => {
    return Math.max(0, Math.min(maxIndex, centerIndex));
  }, [centerIndex, maxIndex]);

  const baseIndexes = useMemo(() => {
    if (extentMode === 'full') {
      const targetCount = targetSliceCountForQuality(quality);
      const fullStep = Math.max(1, Math.ceil((maxIndex + 1) / targetCount));
      const indexes = new Set<number>();

      for (let index = 0; index <= maxIndex; index += fullStep) {
        indexes.add(index);
      }

      indexes.add(maxIndex);
      return [...indexes].sort((a, b) => a - b);
    }

    if (windowSize === 0) return [];

    const safeStep = Math.max(1, step);
    const halfWindow = Math.floor(windowSize / 2);
    const start = Math.max(0, activeIndex - halfWindow);
    const end = Math.min(maxIndex, activeIndex + halfWindow);
    const indexes = new Set<number>();

    for (let index = start; index <= end; index += safeStep) {
      indexes.add(index);
    }

    return [...indexes].sort((a, b) => a - b);
  }, [activeIndex, extentMode, maxIndex, quality, step, windowSize]);

  const baseSignature = useMemo(() => {
    return [
      displaySignature,
      extentMode,
      quality,
      windowSize,
      step,
      baseIndexes.join(','),
    ].join('|');
  }, [baseIndexes, displaySignature, extentMode, quality, step, windowSize]);

  function trimTextureCache() {
    const cache = textureCacheRef.current;
    if (cache.size <= MAX_TEXTURE_CACHE_ENTRIES) return;

    const entries = [...cache.entries()].sort((a, b) => a[1].lastUsed - b[1].lastUsed);
    const removeCount = cache.size - MAX_TEXTURE_CACHE_ENTRIES;

    for (let i = 0; i < removeCount; i += 1) {
      const [key, entry] = entries[i];
      entry.texture.dispose();
      cache.delete(key);
    }
  }

  function getTextureFromCache(index: number, opaqueMode: boolean): THREE.DataTexture | null {
    const cacheKey = makeTextureCacheKey(displaySignature, index, opaqueMode);
    const cached = textureCacheRef.current.get(cacheKey);

    if (!cached) return null;

    cached.lastUsed = performance.now();
    return cached.texture;
  }

  async function getCachedTextureByMode(
    index: number,
    opaqueMode: boolean
  ): Promise<THREE.DataTexture> {
    const existing = getTextureFromCache(index, opaqueMode);
    if (existing) return existing;

    const result = await fetchSlice(zarrPath, dim, index);

    const texture = buildTextureFromSlice(
      result.data,
      result.shape,
      dim,
      amplitudeGain,
      clipPercentile,
      density,
      threshold,
      colorMap,
      waveDisplayMode,
      opaqueMode
    );

    const cacheKey = makeTextureCacheKey(displaySignature, index, opaqueMode);

    textureCacheRef.current.set(cacheKey, {
      texture,
      lastUsed: performance.now(),
    });

    trimTextureCache();

    return texture;
  }

  useEffect(() => {
    let cancelled = false;
    const requestVersion = ++requestVersionRef.current;

    async function loadBaseStack() {
      const loaded: LoadedStackSlice[] = [];
      let batchCount = 0;

      if (baseIndexes.length > 0) {
        onCacheStatus?.({
          loading: true,
          message: 'Caching initial volume...',
        });
      }

      for (const index of baseIndexes) {
        try {
          const texture = await getCachedTextureByMode(index, false);

          if (cancelled || requestVersion !== requestVersionRef.current) return;

          loaded.push({ index, texture, active: false });
          batchCount += 1;

          if (batchCount >= BACKGROUND_BATCH_SIZE) {
            batchCount = 0;
            await idleTick();
          }
        } catch (error) {
          console.error('Failed to load base volume slice', { dim, index, error });
        }
      }

      if (!cancelled && requestVersion === requestVersionRef.current) {
        setBaseSlices(loaded);
        onCacheStatus?.(null);
      }
    }

    loadBaseStack();

    return () => {
      cancelled = true;
    };
  }, [baseSignature, dim, displaySignature, zarrPath]);

  useEffect(() => {
    let cancelled = false;

    async function loadActiveSlice() {
      try {
        const opaqueMode = extentMode === 'full' || windowSize === 0;
        const cached = getTextureFromCache(activeIndex, opaqueMode);

        if (cached) {
          setActiveSlice({ index: activeIndex, texture: cached, active: true });
          onCacheStatus?.(null);
          return;
        }

        onCacheStatus?.({
          loading: true,
          message: 'Caching data...',
        });

        const texture = await getCachedTextureByMode(activeIndex, opaqueMode);

        if (cancelled) return;

        setActiveSlice({ index: activeIndex, texture, active: true });
        onCacheStatus?.(null);
      } catch (error) {
        console.error('Failed to load active volume slice', { dim, index: activeIndex, error });
        onCacheStatus?.(null);
      }
    }

    loadActiveSlice();

    return () => {
      cancelled = true;
    };
  }, [
    activeIndex,
    dim,
    displaySignature,
    extentMode,
    maxIndex,
    onCacheStatus,
    windowSize,
    zarrPath,
  ]);

  useEffect(() => {
    let cancelled = false;

    async function prefetchActiveBlocks() {
      const opaqueMode = extentMode === 'full' || windowSize === 0;
      const indexes = orderIndexesByDistance(
        buildBlockIndexes(activeIndex, maxIndex),
        activeIndex
      );

      const blockSignature = [
        displaySignature,
        extentMode,
        windowSize,
        activeIndex,
        Math.floor(activeIndex / ACTIVE_BLOCK_SIZE),
      ].join('|');

      if (activeBlockSignatureRef.current === blockSignature) return;
      activeBlockSignatureRef.current = blockSignature;

      const range = getBlockRange(activeIndex, maxIndex);
      let missingCount = 0;

      for (const index of indexes) {
        if (!getTextureFromCache(index, opaqueMode)) missingCount += 1;
      }

      if (missingCount > 0) {
        onCacheStatus?.({
          loading: true,
          message: 'Caching data...',
        });
      }

      let loadedInBatch = 0;

      for (const index of indexes) {
        if (cancelled) return;

        try {
          if (!getTextureFromCache(index, opaqueMode)) {
            await getCachedTextureByMode(index, opaqueMode);
            loadedInBatch += 1;
          }

          if (loadedInBatch >= ACTIVE_BLOCK_BATCH_SIZE) {
            loadedInBatch = 0;
            await idleTick();
          }
        } catch {
          // Silent background block-cache failure.
        }
      }

      if (!cancelled) onCacheStatus?.(null);
    }

    prefetchActiveBlocks();

    return () => {
      cancelled = true;
    };
  }, [
    activeIndex,
    dim,
    displaySignature,
    extentMode,
    maxIndex,
    onCacheStatus,
    windowSize,
    zarrPath,
  ]);

  useEffect(() => {
    return () => {
      textureCacheRef.current.forEach((entry) => entry.texture.dispose());
      textureCacheRef.current.clear();
      onCacheStatus?.(null);
    };
  }, [onCacheStatus]);

  const renderedBaseSlices = showBackground ? baseSlices : [];

  const renderedSlices = activeSlice
    ? [
        ...renderedBaseSlices.filter((slice) => slice.index !== activeSlice.index),
        activeSlice,
      ]
    : renderedBaseSlices;

  return (
    <group>
      {renderedSlices.map((slice) => {
        const transform = getPlaneTransform(dim, slice.index, maxIndex, worldSize);
        const opaqueSlice = slice.active && (extentMode === 'full' || windowSize === 0);

        return (
          <mesh
            key={`${dim}-${slice.index}-${slice.active ? 'active' : 'base'}`}
            position={transform.position}
            rotation={transform.rotation}
            renderOrder={slice.active ? 100000 + slice.index : slice.index}
            raycast={() => null}
          >
            <planeGeometry args={transform.planeSize} />
            <meshBasicMaterial
              map={slice.texture}
              transparent={!opaqueSlice}
              opacity={opaqueSlice ? 1 : opacity}
              depthWrite={opaqueSlice}
              depthTest={true}
              side={THREE.DoubleSide}
              toneMapped={false}
              polygonOffset={opaqueSlice}
              polygonOffsetFactor={opaqueSlice ? -2 : 0}
              polygonOffsetUnits={opaqueSlice ? -2 : 0}
            />
          </mesh>
        );
      })}
    </group>
  );
}
