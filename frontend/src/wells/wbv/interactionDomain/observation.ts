import * as THREE from 'three';
import type { WbvScreenObservationV2 } from './contracts';

export function createWbvScreenObservation(
  event: Pick<PointerEvent, 'clientX' | 'clientY'>,
  canvas: HTMLCanvasElement,
  camera: THREE.Camera,
  activationTolerancePx = 20,
  governedTrajectoryTransform?: THREE.Matrix4,
): WbvScreenObservationV2 {
  const rect = canvas.getBoundingClientRect();
  camera.updateMatrixWorld(true);
  const cameraViewProjection = new THREE.Matrix4().multiplyMatrices(
    camera.projectionMatrix,
    camera.matrixWorldInverse,
  );
  // The backend owns trajectory projection and normalizes the governed active
  // trajectory independently. In multi-well view the renderer uses a shared
  // normalization across all displayed trajectories. Compose the active-only
  // to shared-scene transform into the submitted matrix so backend projection
  // evaluates the same visible geometry without accepting frontend-derived
  // trajectory answers.
  const viewProjection = governedTrajectoryTransform
    ? new THREE.Matrix4().multiplyMatrices(cameraViewProjection, governedTrajectoryTransform)
    : cameraViewProjection;
  return {
    pointer_x_px: event.clientX - rect.left,
    pointer_y_px: event.clientY - rect.top,
    viewport_width_px: rect.width,
    viewport_height_px: rect.height,
    view_projection_matrix: [...viewProjection.elements],
    activation_tolerance_px: activationTolerancePx,
  };
}
