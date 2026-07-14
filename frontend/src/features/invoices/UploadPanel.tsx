import type { FormEvent } from "react";
import { FileUp, Loader2 } from "lucide-react";
import { Field } from "../../components/common/Field";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { inputVariants } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
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
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Upload Invoice</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="grid gap-4 md:grid-cols-2" onSubmit={onSubmit}>
          <Field label="Invoice number" name="invoice_number" required />
          <Field label="Currency" name="currency" defaultValue="USD" minLength={3} maxLength={3} required />
          <Field label="Supplier ID" name="supplier_id" placeholder="Optional UUID" />
          <Field label="Total amount" name="total_amount" type="number" step="0.01" min="0" />
          {hasProviders ? (
            <div className="grid gap-1.5">
              <Label htmlFor="provider">Extraction provider</Label>
              <select className={inputVariants} defaultValue={defaultProvider ?? ""} id="provider" name="provider">
                {providers.map((provider) => (
                  <option key={provider.id} value={provider.id} disabled={!provider.available}>
                    {provider.label}
                    {provider.available ? "" : " (no API key)"}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
          {/* accept limits the picker to the document types the extraction pipeline supports. */}
          <div className="grid gap-1.5 md:col-span-2">
            <Label htmlFor="file">Invoice file</Label>
            <input
              className={inputVariants}
              accept="application/pdf,image/png,image/jpeg"
              id="file"
              name="file"
              required
              type="file"
            />
          </div>
          <div className="md:col-span-2">
            <Button disabled={busy} type="submit">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
              Upload and queue
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
