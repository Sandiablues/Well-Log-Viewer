export type TrackHeaderState = 'normal' | 'active' | 'locked';

export type TrackHeaderPresentation = Readonly<{
  state: TrackHeaderState;
  selected: boolean;
  tied: boolean;
  title: string;
  ariaLabel: string;
}>;

export type TrackHeaderIdentity = Readonly<{
  trackId: string;
  trackIndex: number;
}>;

export function buildTrackHeaderPresentationModel(input: Readonly<{
  tracks: readonly TrackHeaderIdentity[];
  stateByTrackId: Readonly<Record<string, TrackHeaderState>>;
  selectedByTrackId: Readonly<Record<string, boolean>>;
  tiedByTrackId: Readonly<Record<string, boolean>>;
}>): Record<string, TrackHeaderPresentation> {
  const presentationByTrackId: Record<string, TrackHeaderPresentation> = {};
  for (const track of input.tracks) {
    const state = input.stateByTrackId[track.trackId] ?? 'normal';
    const selected = input.selectedByTrackId[track.trackId] ?? false;
    const tied = input.tiedByTrackId[track.trackId] ?? false;
    const label = `T${track.trackIndex + 1}`;
    presentationByTrackId[track.trackId] = {
      state,
      selected,
      tied,
      title: state === 'locked'
        ? tied ? `${label} is locked and tied` : `${label} is locked`
        : tied ? `${label} is tied` : label,
      ariaLabel: `Track ${label}: ${state === 'locked' ? 'locked' : 'unlocked'}, ${tied ? 'tied' : 'untied'}`,
    };
  }
  return presentationByTrackId;
}
