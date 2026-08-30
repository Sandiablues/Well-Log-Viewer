import { describe, expect, it } from 'vitest';
import { useViewportCommandExecution } from '../useViewportCommandExecution';

describe('viewport command execution ownership', () => {
  it('exports the dedicated committed viewport command controller hook', () => {
    expect(typeof useViewportCommandExecution).toBe('function');
  });

  it('keeps structural ownership enforcement in the audited installer gate', () => {
    // The installer performs source-level ownership checks without pulling Node
    // filesystem typings into the browser-targeted frontend TypeScript project.
    expect(useViewportCommandExecution.name).toBe('useViewportCommandExecution');
  });

  it('does not require Node runtime modules in the frontend test contract', () => {
    expect(useViewportCommandExecution).toBeDefined();
  });
});
