/** Smoke — verifies the vitest toolchain runs before any real test lands. */
import { describe, expect, it } from 'vitest';

describe('toolchain', () => {
  it('runs', () => {
    expect(1 + 1).toBe(2);
  });
});
