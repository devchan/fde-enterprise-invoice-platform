import { createContext, useContext, type ReactNode } from "react";
import type { useCockpitController } from "./useCockpitController";

type CockpitValue = ReturnType<typeof useCockpitController>;

const CockpitContext = createContext<CockpitValue | null>(null);

export function CockpitProvider({ value, children }: { value: CockpitValue; children: ReactNode }) {
  return <CockpitContext.Provider value={value}>{children}</CockpitContext.Provider>;
}

export function useCockpit(): CockpitValue {
  const context = useContext(CockpitContext);
  if (!context) throw new Error("useCockpit must be used within a CockpitProvider");
  return context;
}
