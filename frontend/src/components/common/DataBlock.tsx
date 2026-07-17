import type { ReactNode } from "react";

// Titled section used to group the invoice detail sub-lists (validation, files,
// etc.). The label uses the mono eyebrow treatment so these read as blueprint
// section markers rather than competing with the invoice heading.
export function DataBlock({ children, title }: { children: ReactNode; title: string }) {
  return (
    <section>
      <h3 className="eyebrow mb-2">{title}</h3>
      <div className="space-y-2">{children}</div>
    </section>
  );
}
