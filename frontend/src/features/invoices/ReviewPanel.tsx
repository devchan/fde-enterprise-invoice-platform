import type { FormEvent } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { CheckCircle2, Download, Loader2, RefreshCw, XCircle } from "lucide-react";
import { DataBlock } from "../../components/common/DataBlock";
import { DataTable } from "../../components/common/DataTable";
import { EmptyPanel } from "../../components/common/EmptyPanel";
import { Field } from "../../components/common/Field";
import { StatusPill } from "../../components/common/StatusPill";
import type { InvoiceDetail, InvoiceFile } from "../../domain/types";
import { formatDate } from "../../utils/format";

export function ReviewPanel({
  busy,
  invoices,
  onOpenFile,
  onRefresh,
  onReview,
  onSelect,
  selectedInvoice,
}: {
  busy: string | null;
  invoices: InvoiceDetail[];
  onOpenFile: (file: InvoiceFile) => void;
  onRefresh: () => void;
  onReview: (decision: "approve" | "reject", event: FormEvent<HTMLFormElement>) => void;
  onSelect: (invoiceId: string) => void;
  selectedInvoice: InvoiceDetail | null;
}) {
  // Defined inside the component so the invoice-number cell can close over onSelect.
  const invoiceColumns: ColumnDef<InvoiceDetail>[] = [
    {
      accessorKey: "invoice_number",
      header: "Invoice",
      cell: ({ row }) => (
        <button
          className="font-medium text-primary"
          onClick={() => onSelect(row.original.invoice_id)}
          type="button"
        >
          {row.original.invoice_number}
        </button>
      ),
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => <StatusPill label={row.original.status} tone={row.original.status === "failed" ? "error" : "info"} />,
    },
    {
      accessorKey: "created_at",
      header: "Created",
      cell: ({ row }) => <span className="text-muted-foreground">{formatDate(row.original.created_at)}</span>,
    },
  ];

  return (
    <section className="grid gap-4 xl:grid-cols-[360px_1fr]">
      <div className="panel">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Invoices</h2>
          <button className="icon-button" onClick={onRefresh} title="Refresh invoices" type="button">
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-4">
          <DataTable columns={invoiceColumns} data={invoices} emptyMessage="No invoices loaded." />
          {selectedInvoice ? (
            <p className="mt-3 text-xs text-muted-foreground">Selected invoice: {selectedInvoice.invoice_number}</p>
          ) : null}
        </div>
      </div>

      <div className="panel">
        {!selectedInvoice ? (
          <EmptyPanel title="Select an invoice to review." />
        ) : (
          <>
            <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
              <div>
                <h2 className="text-xl font-semibold">{selectedInvoice.invoice_number}</h2>
                <p className="text-sm text-muted-foreground">
                  {selectedInvoice.currency} {selectedInvoice.total_amount || "0.00"} · {selectedInvoice.status}
                </p>
              </div>
              <StatusPill label={selectedInvoice.status} tone={selectedInvoice.status === "approved" ? "ok" : selectedInvoice.status === "failed" ? "error" : "info"} />
            </div>

            <form
              className="mt-5 grid gap-4 md:grid-cols-2"
              onSubmit={(event) => {
                // One form, two submit buttons: read the clicked button's value to
                // decide approve vs reject (default to approve if the submitter is unknown).
                const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
                const decision = submitter?.value === "reject" ? "reject" : "approve";
                onReview(decision, event);
              }}
            >
              {/* Prefilled with the extracted values so reviewers edit-in-place to correct them. */}
              <Field label="Invoice number" name="invoice_number" defaultValue={selectedInvoice.invoice_number} />
              <Field label="Invoice date" name="invoice_date" type="date" defaultValue={selectedInvoice.invoice_date || ""} />
              <Field label="Total amount" name="total_amount" type="number" step="0.01" defaultValue={selectedInvoice.total_amount || ""} />
              <Field label="Currency" name="currency" defaultValue={selectedInvoice.currency} />
              <label className="field md:col-span-2">
                <span>Review notes</span>
                <textarea name="notes" rows={3} placeholder="Decision notes" />
              </label>
              <div className="flex flex-wrap gap-2 md:col-span-2">
                <button className="btn-primary" disabled={busy === "review:approve"} name="decision" type="submit" value="approve">
                  <CheckCircle2 className="h-4 w-4" />
                  Approve
                </button>
                <button className="btn-danger" disabled={busy === "review:reject"} name="decision" type="submit" value="reject">
                  <XCircle className="h-4 w-4" />
                  Reject
                </button>
              </div>
            </form>

            <DetailSections invoice={selectedInvoice} busy={busy} onOpenFile={onOpenFile} />
          </>
        )}
      </div>
    </section>
  );
}

function DetailSections({ invoice, busy, onOpenFile }: { invoice: InvoiceDetail; busy: string | null; onOpenFile: (file: InvoiceFile) => void }) {
  return (
    <div className="mt-6 grid gap-4 lg:grid-cols-2">
      <DataBlock title="Validation">
        {invoice.validation_results.length === 0 ? <p className="text-sm text-muted-foreground">No validation results.</p> : null}
        {invoice.validation_results.map((result) => (
          <div className="list-row" key={result.validation_result_id}>
            <span>{result.rule_code}</span>
            <span className={result.passed ? "text-primary" : "text-destructive"}>{result.passed ? "passed" : result.severity}</span>
          </div>
        ))}
      </DataBlock>
      <DataBlock title="Files">
        {invoice.files.map((file) => (
          <button className="list-row" key={file.file_id} onClick={() => onOpenFile(file)} type="button">
            <span>{file.mime_type}</span>
            <span className="flex items-center gap-1 text-primary">
              {busy === `file:${file.file_id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              Open
            </span>
          </button>
        ))}
      </DataBlock>
      <DataBlock title="Line items">
        {invoice.line_items.length === 0 ? <p className="text-sm text-muted-foreground">No line items.</p> : null}
        {invoice.line_items.map((item) => (
          <div className="list-row" key={item.line_item_id}>
            <span>{item.description}</span>
            <span>{item.line_total || "-"}</span>
          </div>
        ))}
      </DataBlock>
      {/* Raw model output shown verbatim so reviewers can audit what the extractor produced. */}
      <DataBlock title="Extraction">
        <pre className="max-h-60 overflow-auto rounded bg-muted p-3 text-xs">
          {JSON.stringify(invoice.latest_extraction?.extracted_payload || {}, null, 2)}
        </pre>
      </DataBlock>
    </div>
  );
}
