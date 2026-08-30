import * as THREE from 'three';

// WBV_TOPSIDE_RIG_LUMINOSITY_REDUCTION_V1_0_3
export function createWbvTopsideRig(
  scale = 1,
  color: THREE.ColorRepresentation = 0xaed0d3,
): THREE.Group {
  const rig = new THREE.Group();
  rig.name = 'wbv-topside-rig';

  const points: THREE.Vector3[] = [];
  const addSegment = (
    ax: number, ay: number, az: number,
    bx: number, by: number, bz: number,
  ) => {
    points.push(
      new THREE.Vector3(ax * scale, ay * scale, az * scale),
      new THREE.Vector3(bx * scale, by * scale, bz * scale),
    );
  };

  const deckMinX = -0.34;
  const deckMaxX = 0.34;
  const deckMinZ = -0.22;
  const deckMaxZ = 0.22;
  const deckY = 0.12;

  addSegment(deckMinX, deckY, deckMinZ, deckMaxX, deckY, deckMinZ);
  addSegment(deckMaxX, deckY, deckMinZ, deckMaxX, deckY, deckMaxZ);
  addSegment(deckMaxX, deckY, deckMaxZ, deckMinX, deckY, deckMaxZ);
  addSegment(deckMinX, deckY, deckMaxZ, deckMinX, deckY, deckMinZ);
  addSegment(deckMinX, deckY, 0, deckMaxX, deckY, 0);
  addSegment(0, deckY, deckMinZ, 0, deckY, deckMaxZ);

  const legCorners: Array<[number, number]> = [
    [deckMinX, deckMinZ],
    [deckMaxX, deckMinZ],
    [deckMaxX, deckMaxZ],
    [deckMinX, deckMaxZ],
  ];
  for (const [x, z] of legCorners) {
    addSegment(x, 0, z, x, deckY, z);
  }
  addSegment(deckMinX, 0, deckMinZ, deckMaxX, deckY, deckMinZ);
  addSegment(deckMaxX, 0, deckMinZ, deckMinX, deckY, deckMinZ);
  addSegment(deckMinX, 0, deckMaxZ, deckMaxX, deckY, deckMaxZ);
  addSegment(deckMaxX, 0, deckMaxZ, deckMinX, deckY, deckMaxZ);

  const derrickBaseY = deckY;
  const derrickTopY = 0.80;
  const derrickLevels = [derrickBaseY, 0.30, 0.47, 0.63, derrickTopY];

  const halfWidthAt = (y: number) => {
    const start = 0.15;
    const end = 0.055;
    const ratio = (y - derrickBaseY) / (derrickTopY - derrickBaseY);
    return start + (end - start) * ratio;
  };

  const cornersAt = (y: number): Array<[number, number, number]> => {
    const h = halfWidthAt(y);
    return [
      [-h, y, -h],
      [ h, y, -h],
      [ h, y,  h],
      [-h, y,  h],
    ];
  };

  for (let i = 0; i < derrickLevels.length; i += 1) {
    const current = cornersAt(derrickLevels[i]);
    for (let j = 0; j < 4; j += 1) {
      const a = current[j];
      const b = current[(j + 1) % 4];
      addSegment(a[0], a[1], a[2], b[0], b[1], b[2]);
    }
    if (i < derrickLevels.length - 1) {
      const next = cornersAt(derrickLevels[i + 1]);
      for (let j = 0; j < 4; j += 1) {
        const a = current[j];
        const b = next[j];
        const cross = next[(j + 1) % 4];
        addSegment(a[0], a[1], a[2], b[0], b[1], b[2]);
        addSegment(a[0], a[1], a[2], cross[0], cross[1], cross[2]);
      }
    }
  }

  addSegment(0, 0, 0, 0, derrickTopY + 0.04, 0);

  const moduleCorners: Array<[number, number, number]> = [
    [-0.30, deckY, -0.18],
    [-0.12, deckY, -0.18],
    [-0.12, deckY,  0.00],
    [-0.30, deckY,  0.00],
    [-0.30, deckY + 0.14, -0.18],
    [-0.12, deckY + 0.14, -0.18],
    [-0.12, deckY + 0.14,  0.00],
    [-0.30, deckY + 0.14,  0.00],
  ];
  const moduleEdges: Array<[number, number]> = [
    [0,1],[1,2],[2,3],[3,0],
    [4,5],[5,6],[6,7],[7,4],
    [0,4],[1,5],[2,6],[3,7],
  ];
  for (const [a, b] of moduleEdges) {
    const p = moduleCorners[a];
    const q = moduleCorners[b];
    addSegment(p[0], p[1], p[2], q[0], q[1], q[2]);
  }

  addSegment(0.25, deckY, -0.10, 0.25, deckY + 0.28, -0.10);
  addSegment(0.25, deckY + 0.27, -0.10, 0.54, deckY + 0.39, -0.10);
  addSegment(0.54, deckY + 0.39, -0.10, 0.54, deckY + 0.18, -0.10);

  const geometry = new THREE.BufferGeometry().setFromPoints(points);

  const primaryMaterial = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity: 0.5984,
    depthTest: false,
    depthWrite: false,
  });
  const primary = new THREE.LineSegments(geometry, primaryMaterial);
  primary.name = 'wbv-topside-rig-wireframe';
  primary.renderOrder = 20;
  rig.add(primary);

  const glowMaterial = new THREE.LineBasicMaterial({
    color: 0x6fbbc3,
    transparent: true,
    opacity: 0.2856,
    depthTest: false,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const glow = new THREE.LineSegments(geometry.clone(), glowMaterial);
  glow.name = 'wbv-topside-rig-glow';
  glow.renderOrder = 21;
  rig.add(glow);

  return rig;
}
