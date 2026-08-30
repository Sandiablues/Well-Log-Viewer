import { describe, expect, it, vi } from 'vitest';
import {
  SelectedPointTrackingController,
  type TrackingBackendCommand,
  type TrackingTrajectoryStation,
} from '../selectedPointTracking/selectedPointTrackingController';

type Point = { md: number; tvd: number; x: number; y: number; z: number };
type Observation = { x: number; y: number };
type State = { active_tracking_session_id: string | null; revision: number };

const stations = (): TrackingTrajectoryStation<Point>[] => [
  { point: { md: 0, tvd: 0, x: 0, y: 0, z: 0 }, segmentOrder: 0, sceneX: 0, sceneY: 0, sceneZ: 0, screenX: 0, screenY: 0 },
  { point: { md: 100, tvd: 100, x: 1, y: 0, z: 0 }, segmentOrder: 1, sceneX: 1, sceneY: 0, sceneZ: 0, screenX: 100, screenY: 0 },
  { point: { md: 200, tvd: 200, x: 2, y: 0, z: 0 }, segmentOrder: 2, sceneX: 2, sceneY: 0, sceneZ: 0, screenX: 200, screenY: 0 },
  { point: { md: 300, tvd: 300, x: 3, y: 0, z: 0 }, segmentOrder: 3, sceneX: 3, sceneY: 0, sceneZ: 0, screenX: 100, screenY: 0 },
];

const interpolate = (first: Point, second: Point, ratio: number): Point => ({
  md: first.md + (second.md - first.md) * ratio,
  tvd: first.tvd + (second.tvd - first.tvd) * ratio,
  x: first.x + (second.x - first.x) * ratio,
  y: first.y + (second.y - first.y) * ratio,
  z: first.z + (second.z - first.z) * ratio,
});

describe('SelectedPointTrackingController enterprise contract', () => {
  it('starts globally then remains on the local trajectory branch at a projected crossing', async () => {
    const shown: number[] = [];
    const controller = new SelectedPointTrackingController<Point, Observation, State>({
      projectStations: stations,
      interpolatePoint: interpolate,
      sendCommand: vi.fn(async (command: TrackingBackendCommand<Observation>) => ({
        active_tracking_session_id: command.kind === 'track-commit' || command.kind === 'track-cancel' ? null : 'session',
        revision: 1,
      })),
      showTransient: (location) => shown.push(location.point.md),
      clearTransient: vi.fn(),
      reconcileCommitted: vi.fn(),
      setOrbitEnabled: vi.fn(),
      policy: {
        localSegmentRadius: 1,
        maximumArcAdvancePerObservation: 1.25,
        continuityPenaltyPx: 10,
        globalHitTolerancePx: 30,
      },
    });

    await controller.start(1, { x: 10, y: 0 }, { x: 10, y: 0 });
    controller.move(1, { x: 100, y: 0 }, { x: 100, y: 0 });

    expect(shown[0]).toBeCloseTo(10, 6);
    expect(shown[shown.length - 1]).toBeLessThanOrEqual(200);
  });

  it('updates transient presentation without waiting for backend confirmation', async () => {
    let resolveStart!: (state: State) => void;
    const startGate = new Promise<State>((resolve) => { resolveStart = resolve; });
    const shown: number[] = [];
    const controller = new SelectedPointTrackingController<Point, Observation, State>({
      projectStations: stations,
      interpolatePoint: interpolate,
      sendCommand: vi.fn(async (command) => command.kind === 'track-start'
        ? startGate
        : { active_tracking_session_id: 'session', revision: 1 }),
      showTransient: (location) => shown.push(location.point.md),
      clearTransient: vi.fn(),
      reconcileCommitted: vi.fn(),
      setOrbitEnabled: vi.fn(),
    });

    const starting = controller.start(1, { x: 10, y: 0 }, { x: 10, y: 0 });
    controller.move(1, { x: 40, y: 0 }, { x: 40, y: 0 });
    expect(shown[shown.length - 1]).toBeCloseTo(40, 6);
    resolveStart({ active_tracking_session_id: 'session', revision: 1 });
    await starting;
  });

  it('coalesces backend updates to one in-flight request plus the latest observation', async () => {
    const updates: Observation[] = [];
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const controller = new SelectedPointTrackingController<Point, Observation, State>({
      projectStations: stations,
      interpolatePoint: interpolate,
      sendCommand: vi.fn(async (command) => {
        if (command.kind === 'track-update') {
          updates.push(command.observation);
          if (updates.length === 1) await gate;
        }
        return { active_tracking_session_id: 'session', revision: 1 };
      }),
      showTransient: vi.fn(),
      clearTransient: vi.fn(),
      reconcileCommitted: vi.fn(),
      setOrbitEnabled: vi.fn(),
    });

    await controller.start(1, { x: 10, y: 0 }, { x: 10, y: 0 });
    controller.move(1, { x: 20, y: 0 }, { x: 20, y: 0 });
    controller.move(1, { x: 30, y: 0 }, { x: 30, y: 0 });
    controller.move(1, { x: 40, y: 0 }, { x: 40, y: 0 });
    release();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(updates).toEqual([{ x: 20, y: 0 }, { x: 40, y: 0 }]);
  });

  it('restores orbit and reconciles only after backend commit', async () => {
    const orbit: boolean[] = [];
    const reconcile = vi.fn();
    const controller = new SelectedPointTrackingController<Point, Observation, State>({
      projectStations: stations,
      interpolatePoint: interpolate,
      sendCommand: vi.fn(async (command) => ({
        active_tracking_session_id: command.kind === 'track-commit' ? null : 'session',
        revision: command.kind === 'track-commit' ? 2 : 1,
      })),
      showTransient: vi.fn(),
      clearTransient: vi.fn(),
      reconcileCommitted: reconcile,
      setOrbitEnabled: (enabled) => orbit.push(enabled),
    });

    await controller.start(1, { x: 10, y: 0 }, { x: 10, y: 0 });
    await controller.commit(1, { x: 80, y: 0 });

    expect(orbit).toEqual([false, true]);
    expect(reconcile).toHaveBeenCalledWith({ active_tracking_session_id: null, revision: 2 });
    expect(controller.state).toBe('idle');
  });

  it('cleans up on cancel and dispose', async () => {
    const clear = vi.fn();
    const orbit: boolean[] = [];
    const controller = new SelectedPointTrackingController<Point, Observation, State>({
      projectStations: stations,
      interpolatePoint: interpolate,
      sendCommand: vi.fn(async (command) => ({
        active_tracking_session_id: command.kind === 'track-cancel' ? null : 'session',
        revision: 1,
      })),
      showTransient: vi.fn(),
      clearTransient: clear,
      reconcileCommitted: vi.fn(),
      setOrbitEnabled: (enabled) => orbit.push(enabled),
    });

    await controller.start(4, { x: 10, y: 0 }, { x: 10, y: 0 });
    await controller.cancel(4);
    controller.dispose();

    expect(clear).toHaveBeenCalled();
    expect(orbit[orbit.length - 1]).toBe(true);
    expect(controller.state).toBe('disposed');
  });
});
