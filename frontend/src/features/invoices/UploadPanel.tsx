import type { FormEvent } from "react";
import { FileUp, Loader2 } from "lucide-react";
import { Field } from "../../components/common/Field";
import type { ExtractionProvider } from "../../domain/types";

export function UploadPanel({
  busy,
  onSubmit,
  providers,
  defaultProvider,
}: {
  busy: boolean;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  providers: ExtractionProvider[];
  defaultProvider: string | null;
}) {
  // A provider with no server-side API key is shown but disabled so it can't be
  // selected. Default the dropdown to the server's suggested (available) provider.
  const hasProviders = providers.length > 0;
  return (
    <section className="panel">
      <h2 className="text-lg font-semibold">Upload Invoice</h2>
      <form className="mt-4 grid gap-4 md:grid-cols-2" onSubmit={onSubmit}>
        <Field label="Invoice number" name="invoice_number" required />
        <Field label="Currency" name="currency" defaultValue="USD" minLength={3} maxLength={3} required />
        <Field label="Supplier ID" name="supplier_id" placeholder="Optional UUID" />
        <Field label="Total amount" name="total_amount" type="number" step="0.01" min="0" />
        {hasProviders ? (
          <label className="field">
            <span>Extraction provider</span>
            <select name="provider" defaultValue={defaultProvider ?? ""}>
              {providers.map((provider) => (
                <option key={provider.id} value={provider.id} disabled={!provider.available}>
                  {provider.label}
                  {provider.available ? "" : " (no API key)"}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {/* accept limits the picker to the document types the extraction pipeline supports. */}
        <label className="field md:col-span-2">
          <span>Invoice file</span>
          <input name="file" required type="file" accept="application/pdf,image/png,image/jpeg" />
        </label>
        <div className="md:col-span-2">
          <button className="btn-primary" disabled={busy} type="submit">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
            Upload and queue
          </button>
        </div>
      </form>
    </section>
  );
}
