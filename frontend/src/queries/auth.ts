import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useToast } from "../app/ToastContext";
import type { LoginCredentials, Session } from "../domain/types";
import { authService } from "../services";
import { errorMessage } from "../utils/form";
import { sessionKeys } from "./keys";

// me() throwing just means "no valid cookie session" — routine on first load while
// signed out, not an exceptional condition, so no retry and no error toast for it.
export function useSessionQuery() {
  return useQuery({
    queryKey: sessionKeys.me(),
    queryFn: () => authService.me(),
    retry: false,
    staleTime: Infinity,
  });
}

export function useLoginMutation() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { setToast } = useToast();

  return useMutation({
    mutationFn: (credentials: LoginCredentials) => authService.login(credentials.email.trim(), credentials.password),
    onSuccess: (session) => {
      queryClient.setQueryData(sessionKeys.me(), session);
      void navigate({ to: "/" });
      setToast({ message: `Signed in as ${session.email}`, tone: "ok" });
    },
    onError: (error) => {
      setToast({ message: errorMessage(error), tone: "error" });
    },
  });
}

export function useLogoutMutation() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { setToast } = useToast();

  return useMutation({
    // Revoke server-side (best-effort) so the tokens cannot be replayed.
    mutationFn: () => authService.logout().catch(() => undefined),
    onSuccess: () => {
      queryClient.setQueryData(sessionKeys.me(), null);
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "session" });
      void navigate({ to: "/" });
      setToast({ message: "Signed out.", tone: "info" });
    },
  });
}

export function useChangeOwnPasswordMutation() {
  const { setToast } = useToast();

  return useMutation({
    mutationFn: (payload: { session: Session; currentPassword: string; newPassword: string }) =>
      authService.changeOwnPassword(payload.session, payload.currentPassword, payload.newPassword),
    onSuccess: () => {
      setToast({ message: "Password changed.", tone: "ok" });
    },
    onError: (error) => {
      setToast({ message: errorMessage(error), tone: "error" });
    },
  });
}
