import { createContext, useContext, useState, type ReactNode } from "react";

export type ToastState = { message: string; tone: "ok" | "error" | "info" } | null;

type ToastContextValue = {
  toast: ToastState;
  setToast: (toast: ToastState) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastState>(null);
  return <ToastContext.Provider value={{ toast, setToast }}>{children}</ToastContext.Provider>;
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within a ToastProvider");
  return context;
}
