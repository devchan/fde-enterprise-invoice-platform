import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useToast } from "../app/ToastContext";
import type { Session, UserRecord } from "../domain/types";
import { userService } from "../services";
import { errorMessage } from "../utils/form";
import { auditKeys, userKeys } from "./keys";

export function useUsersQuery(session: Session | null) {
  return useQuery({
    queryKey: userKeys.list(session?.organization_id ?? ""),
    queryFn: () => userService.list(session as Session),
    enabled: Boolean(session && session.role === "admin"),
  });
}

export function useCreateUserMutation(session: Session | null) {
  const queryClient = useQueryClient();
  const { setToast } = useToast();
  const orgId = session?.organization_id ?? "";

  return useMutation({
    mutationFn: (payload: { email: string; role: string; password: string }) => userService.create(session as Session, payload),
    onSuccess: () => {
      setToast({ message: "User created.", tone: "ok" });
      void queryClient.invalidateQueries({ queryKey: userKeys.list(orgId) });
      void queryClient.invalidateQueries({ queryKey: auditKeys.all(orgId) });
    },
    onError: (error) => {
      setToast({ message: errorMessage(error), tone: "error" });
    },
  });
}

export function useUpdateUserMutation(session: Session | null) {
  const queryClient = useQueryClient();
  const { setToast } = useToast();
  const orgId = session?.organization_id ?? "";

  return useMutation({
    mutationFn: (payload: { user: UserRecord; email: string; role: string }) =>
      userService.update(session as Session, payload.user, { email: payload.email, role: payload.role }),
    onSuccess: () => {
      setToast({ message: "User updated.", tone: "ok" });
      void queryClient.invalidateQueries({ queryKey: userKeys.list(orgId) });
      void queryClient.invalidateQueries({ queryKey: auditKeys.all(orgId) });
      // If admins edit their own record, mirror the change into the live session immediately.
      void queryClient.invalidateQueries({ queryKey: ["session"] });
    },
    onError: (error) => {
      setToast({ message: errorMessage(error), tone: "error" });
    },
  });
}

export function useResetPasswordMutation(session: Session | null) {
  const { setToast } = useToast();

  return useMutation({
    mutationFn: (payload: { user: UserRecord; password: string }) =>
      userService.resetPassword(session as Session, payload.user, payload.password),
    onSuccess: () => {
      setToast({ message: "Password reset.", tone: "ok" });
    },
    onError: (error) => {
      setToast({ message: errorMessage(error), tone: "error" });
    },
  });
}
