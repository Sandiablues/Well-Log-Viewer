import { describe, expect, it } from 'vitest';
import rendererSource from '../WellboreTrajectoryRenderer.tsx?raw';

describe('WBV Shift + MB1 selected-point contract', () => {
  it('keeps one authoritative interaction lifecycle across backend rerenders', () => {
    expect(rendererSource).toContain('const interactionLifecycleRef = useRef<');
    expect(rendererSource).toContain('const onInteractionCommandRef = useRef(onInteractionCommand)');
    expect(rendererSource).toContain('onInteractionCommandRef.current = onInteractionCommand');
    expect(rendererSource).toContain('const sendCommand = async');
    expect(rendererSource).toContain('const interactionLifecycle = interactionLifecycleRef.current');
    expect(rendererSource).toContain('trackingStartPromise');
    expect(rendererSource).toContain('trackingUpdatePromise');
    expect(rendererSource).toContain('pendingTrackingObservation');
  });

  it('uses an always-front screen-facing bullseye sprite', () => {
    expect(rendererSource).toContain('new THREE.SpriteMaterial');
    expect(rendererSource).toContain('depthTest: false');
    expect(rendererSource).toContain('depthWrite: false');
    expect(rendererSource).toContain('const marker = new THREE.Sprite(material)');
    expect(rendererSource).toContain('marker.renderOrder = 200');
    expect(rendererSource).toContain('markerScaleForZoom(camera.zoom)');
    expect(rendererSource).not.toContain('new THREE.RingGeometry');
  });

  it('renders continuity-controlled transient movement while preserving backend cadence', () => {
    expect(rendererSource).toContain('new TransientContinuityController');
    expect(rendererSource).toContain('startTransientContinuity(event)');
    expect(rendererSource).toContain('updateTransientContinuity(event)');
    expect(rendererSource).toContain('activeTransientPoint = location.point');
    expect(rendererSource).toContain('advanceTransientArcPresentation(');
    expect(rendererSource).toContain('transientContinuity.locationAtArc(displayedTransientProjectedDistance)');
    expect(rendererSource).toContain('const point = activeTransientPoint ?? selectedPointRef.current');
    expect(rendererSource).toContain('interactionLifecycle.pendingTrackingObservation = observation');
    expect(rendererSource).toContain('flushTrackingUpdate()');
    expect(rendererSource).not.toContain('DRAG_BACKEND_INTERVAL_MS');
    expect(rendererSource).not.toContain('pointerrawupdate');
    expect(rendererSource).not.toContain('getCoalescedEvents');
  });

  it('preserves the existing user gesture and backend command lifecycle', () => {
    expect(rendererSource).toContain("event.shiftKey && selectionModeRef.current === 'point'");
    expect(rendererSource).toContain("kind: 'track-start'");
    expect(rendererSource).toContain("kind: 'track-update'");
    expect(rendererSource).toContain("kind: commit ? 'track-commit' : 'track-cancel'");
    expect(rendererSource).toContain("kind: 'observe'");
  });

  it('freezes orbit only for active tracking and restores it on completion', () => {
    expect(rendererSource).toContain('if (controls) controls.enabled = false');
    expect(rendererSource).toContain('if (controls) controls.enabled = true');
    expect(rendererSource).toContain('renderer.domElement.setPointerCapture(event.pointerId)');
    expect(rendererSource).toContain('renderer.domElement.releasePointerCapture(event.pointerId)');
  });
  it('uses the normal arrow cursor instead of a hand or grab motif', () => {
    expect(rendererSource).toContain("renderer.domElement.style.cursor = 'default'");
    expect(rendererSource).toContain("renderer?.domElement.style.setProperty('cursor', 'default')");
    expect(rendererSource).not.toContain("style.cursor = 'grab'");
    expect(rendererSource).not.toContain("style.cursor = 'grabbing'");
    expect(rendererSource).not.toContain("style.cursor = 'pointer'");
  });

  it('uses a direct fixed-size sphere for selected-point marker diagnostics', () => {
    expect(rendererSource).toContain('const selectionMarker = createDiagnosticSphere()');
    expect(rendererSource).toContain('new THREE.SphereGeometry(0.028, 20, 14)');
    expect(rendererSource).toContain('marker.position.copy(basePosition)');
    expect(rendererSource).toContain('[intervalStartMarker, intervalEndMarker].forEach((marker) => {');
  });

  it('feeds the active selected marker and readout from the same frame location', () => {
    expect(rendererSource).toContain('selectionMarker.position.set(location.sceneX, location.sceneY, location.sceneZ)');
    expect(rendererSource).toContain('if (marker === selectionMarker && transientContinuity) return');
    expect(rendererSource).not.toContain('setMarkerBasePosition(\n          selectionMarker,\n          new THREE.Vector3(location.sceneX, location.sceneY, location.sceneZ)');
  });


  it('supports Shift plus arrow keyboard traversal independent of pointer movement', () => {
    expect(rendererSource).toContain("event.key !== 'ArrowUp' && event.key !== 'ArrowDown'");
    expect(rendererSource).toContain("event.key === 'ArrowUp' ? 1 : -1");
    expect(rendererSource).toContain('keyboardTraversalStepPx = 0.75');
    expect(rendererSource).toContain('transientContinuity.locationAtArc(keyboardTraversalProjectedDistance)');
    expect(rendererSource).toContain("window.addEventListener('keydown', handleKeyboardTraversal)");
    expect(rendererSource).toContain("window.removeEventListener('keydown', handleKeyboardTraversal)");
  });

  it('initializes keyboard traversal from the selected point without an active mouse drag', () => {
    expect(rendererSource).toContain('if (!transientContinuity) {');
    expect(rendererSource).toContain('selectedPointRef.current');
    expect(rendererSource).toContain('transientContinuity = new TransientContinuityController');
    expect(rendererSource).toContain('seededProjectedDistance');
    expect(rendererSource).not.toContain('if (!transientContinuity) return;');
  });

  it('keeps the live annotation rigid in screen space', () => {
    expect(rendererSource).toContain('liveOverlayOffsetXPx = 144');
    expect(rendererSource).toContain('liveOverlayLeaderLengthPx = 128');
    expect(rendererSource).toContain('liveOverlayReadoutWidthPx = 300');
    expect(rendererSource).toContain("readoutElement.style.fontVariantNumeric = 'tabular-nums'");
    expect(rendererSource).toContain('const markerX = Math.round');
    expect(rendererSource).toContain('const readoutLeft = markerX + liveOverlayOffsetXPx');
    expect(rendererSource).not.toContain('const placeLeft = markerX > viewportWidth * 0.68');
    expect(rendererSource).not.toContain('const lineWidth = 64');
  });

  it('uses one uniformly sampled curved display trajectory for rendering and tracking', () => {
    expect(rendererSource).toContain('buildUniformCurveDisplayTrajectory');
    expect(rendererSource).toContain('displayTrajectoryPositions');
    expect(rendererSource).toContain('setFromPoints(displayTrajectoryPositions)');
    expect(rendererSource).toContain('return displayTrajectory.map((sample) => {');
    expect(rendererSource).not.toContain('SEG ${location.segmentIndex}');
    expect(rendererSource).not.toContain('diagnosticFlashUntil');
  });

});
