import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

// The minimal invoice reference the assistant needs for its "why is this
// stuck?" quick action. Pages set it so the globally-mounted assistant stays
// aware of what the user is currently looking at, without the widget having to
// know about routes.
export type AssistantInvoiceContext = { invoice_id: string; invoice_number: string };

type AssistantContextValue = {
  open: boolean;
  setOpen: (open: boolean) => void;
  contextInvoice: AssistantInvoiceContext | null;
  setContextInvoice: (invoice: AssistantInvoiceContext | null) => void;
};

const AssistantContext = createContext<AssistantContextValue | null>(null);

// Holds the shared state for the floating assistant so any screen can open it
// (e.g. the command palette) and route-scoped panels can hand it context.
export function AssistantProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [contextInvoice, setContextInvoice] = useState<AssistantInvoiceContext | null>(null);
  const value = useMemo(
    () => ({ open, setOpen, contextInvoice, setContextInvoice }),
    [open, contextInvoice],
  );
  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
}

export function useAssistant(): AssistantContextValue {
  const context = useContext(AssistantContext);
  if (!context) throw new Error("useAssistant must be used within an AssistantProvider");
  return context;
}
