export function getDatasetShape(volume: any): any[] | null {
  return volume?.metadata?.shape || volume?.metadata?.zarr?.shape || null;
}

export function is3DVolume(volume: any): boolean {
  const shape = getDatasetShape(volume);

  return (
    Array.isArray(shape) &&
    shape.length === 3 &&
    volume?.dataset_type !== '2d_survey'
  );
}

export function is2DLine(volume: any): boolean {
  const shape = getDatasetShape(volume);

  return (
    Array.isArray(shape) &&
    shape.length === 2 &&
    (volume?.dataset_type === '2d_line' || volume?.metadata?.is_3d === false)
  );
}

export function is2DSurvey(volume: any): boolean {
  return volume?.dataset_type === '2d_survey';
}

export function is2DDataset(volume: any): boolean {
  return is2DLine(volume) || is2DSurvey(volume);
}

export function isDisplayableDataset(volume: any): boolean {
  if (volume?.hidden) return false;
  return is3DVolume(volume) || is2DDataset(volume);
}
