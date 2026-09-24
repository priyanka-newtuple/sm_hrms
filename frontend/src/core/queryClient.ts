import { QueryClient } from '@tanstack/react-query';

// Several independent hooks/contexts poll the same list endpoints (workflows,
// entity types, etc.) on mount — a non-zero staleTime lets React Query
// dedupe/reuse those instead of refetching on every mount. Instantiated once
// here (rather than inside App.tsx) so SkinProvider — which mounts above
// <App /> in main.tsx and also reads from React Query — shares this same
// client instead of throwing "No QueryClient set" for lack of a provider.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 30 * 60 * 1000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});
