import type { ReactNode } from "react";

// Titled section used to group the invoice detail sub-lists (validation, files, etc.).
export function DataBlock({ children, title }: { children: ReactNode; title: string }) {
  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      <div className="space-y-2">{children}</div>
    </section>
  );
}
