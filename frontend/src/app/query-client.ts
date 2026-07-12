import { QueryClient } from "@tanstack/react-query";

// Conservative defaults for an operator tool: avoid surprise refetches and
// avoid retrying state-changing calls.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false, // operators tab away constantly; don't refetch on every focus
      retry: 1, // one retry smooths transient network blips without masking real failures
      staleTime: 20_000, // treat data as fresh for 20s to cut redundant fetches
    },
    mutations: {
      retry: 0, // never auto-retry mutations (uploads/reviews) to avoid duplicate side effects
    },
  },
});
