import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = readFileSync(resolve(process.cwd(), 'src/wells/wbv/Wellbore3DPage.tsx'), 'utf8');

describe('WBV selected-point renderer lifecycle stability', () => {
  it('memoizes depth-track render input outside JSX', () => {
    expect(source).toContain('const depthTrackRenderLayout = useMemo(');
    expect(source).toContain('depthTracks={depthTrackRenderLayout}');
  });

  it('does not allocate a filtered depth-track array in renderer props', () => {
    const rendererStart = source.indexOf('<WellboreTrajectoryRenderer');
    const rendererEnd = source.indexOf('/>', rendererStart);
    const rendererProps = source.slice(rendererStart, rendererEnd);
    expect(rendererProps).not.toContain('depthTracks={(wbvTrackLayout?.tracks ?? []).filter(');
  });

  it('keys the memo only to backend-owned track-layout data', () => {
    const memoStart = source.indexOf('const depthTrackRenderLayout = useMemo(');
    const memoEnd = source.indexOf('\n  );', memoStart) + 5;
    const memoBlock = source.slice(memoStart, memoEnd);
    expect(memoBlock).toContain('[wbvTrackLayout?.tracks]');
    expect(memoBlock).not.toContain('selectedPoint');
    expect(memoBlock).not.toContain('interaction');
  });
});
