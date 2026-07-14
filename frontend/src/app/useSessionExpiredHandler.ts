import { useEffect } from "react";
import { useLogoutMutation } from "../queries/auth";
import { registerSessionExpiredHandler } from "./query-client";
import { useToast } from "./ToastContext";

// Mounted exactly once, in __root.tsx: reacts to a SessionExpiredError thrown by any
// query/mutation anywhere by tearing down the session and notifying the user.
export function useSessionExpiredHandler(): void {
  const logoutMutation = useLogoutMutation();
  const { setToast } = useToast();

  useEffect(() => {
    registerSessionExpiredHandler(() => {
      logoutMutation.mutate(undefined, {
        onSuccess: () => setToast({ message: "Your session expired. Sign in again to continue.", tone: "error" }),
      });
    });
  }, [logoutMutation, setToast]);
}
