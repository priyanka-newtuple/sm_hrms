import { afterEach, describe, expect, it, vi } from 'vitest';
import { createRequestId } from './requestId';

const getRandomValues = globalThis.crypto.getRandomValues.bind(globalThis.crypto);
afterEach(() => vi.unstubAllGlobals());

describe('HRMS request IDs', () => {
  it('uses the native UUID API when available', () => {
    const randomUUID = vi.fn(() => 'c99c2f97-a638-492f-b8e7-d483878e7b01');
    vi.stubGlobal('crypto', { randomUUID });
    expect(createRequestId()).toBe('c99c2f97-a638-492f-b8e7-d483878e7b01');
    expect(randomUUID).toHaveBeenCalledOnce();
  });

  it('generates distinct UUID v4 keys on HTTP without randomUUID', () => {
    vi.stubGlobal('crypto', { getRandomValues });
    const ids = Array.from({ length: 100 }, createRequestId);
    for (const id of ids) {
      expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    }
    expect(new Set(ids).size).toBe(ids.length);
  });
});
