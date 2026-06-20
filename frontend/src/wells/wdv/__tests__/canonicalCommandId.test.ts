import { describe, expect, it, vi } from 'vitest';
import {
  createCanonicalCommandId,
  isCanonicalCommandId,
} from '../canonicalCommandId';

describe('canonical command UUIDv7', () => {
  it('creates RFC-compatible UUIDv7 values', () => {
    const values = new Uint8Array(16).fill(0xaa);
    vi.stubGlobal('crypto', {
      getRandomValues: (target: Uint8Array) => {
        target.set(values);
        return target;
      },
    });

    const commandId = createCanonicalCommandId(1_718_000_000_000);
    expect(isCanonicalCommandId(commandId)).toBe(true);
    expect(commandId[14]).toBe('7');
    expect(['8', '9', 'a', 'b']).toContain(commandId[19]);

    vi.unstubAllGlobals();
  });
});
