import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { SessionExpiredError } from "../services/api-client";

// Set by useSession() once, so any query/mutation anywhere can uniformly tear down
// the session on a SessionExpiredError without every call site handling it individually.
let onSessionExpired: (() => void) | null = null;

export function registerSessionExpiredHandler(handler: () => void): void {
  onSessionExpired = handler;
}

function handleGlobalError(error: unknown): void {
  if (error instanceof SessionExpiredError) {
    onSessionExpired?.();
  }
}

// Conservative defaults for an operator tool: avoid surprise refetches and
// avoid retrying state-changing calls.
export const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: handleGlobalError }),
  mutationCache: new MutationCache({ onError: handleGlobalError }),
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
