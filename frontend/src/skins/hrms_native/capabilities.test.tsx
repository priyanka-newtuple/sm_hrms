import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { request } from '../../core/services/api/client';
import { useHrmsCapabilities } from './capabilities';

vi.mock('../../core/services/api/client', () => ({ request: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('native permission refresh', () => {
  it.each([true, false])('clears previously authorized data only when grants change: %s', async changed => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const before = { capabilities: ['project:view'], roles: [], permission_revision: 'old' };
    const next = { ...before, permission_revision: changed ? 'new' : 'old' };
    client.setQueryData(['hrms', 'capabilities'], before);
    client.setQueryData(['hrms', 'projects'], ['private project']);
    client.setQueryData(['unrelated'], ['keep']);
    vi.mocked(request).mockResolvedValue(next);
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result, unmount } = renderHook(() => useHrmsCapabilities(), { wrapper });
    await waitFor(() => expect(result.current.isFetching).toBe(false));
    expect(client.getQueryData(['hrms', 'projects'])).toEqual(changed ? undefined : ['private project']);
    expect(client.getQueryData(['unrelated'])).toEqual(['keep']);
    expect(result.current.data).toEqual(next);
    expect(request).toHaveBeenCalledTimes(1);
    unmount();
    client.clear();
  });
});
