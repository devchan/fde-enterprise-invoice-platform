import { useRef, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { CheckCircle2, Download, Loader2, RefreshCw, XCircle } from "lucide-react";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { DataBlock } from "../../components/common/DataBlock";
import { DataTable } from "../../components/common/DataTable";
import { EmptyPanel } from "../../components/common/EmptyPanel";
import { Field } from "../../components/common/Field";
import { StatusPill } from "../../components/common/StatusPill";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import type { InvoiceDetail, InvoiceFile, SimilarInvoice } from "../../domain/types";
import { formatDate } from "../../utils/format";

export function ReviewPanel({
  invoices,
  isApproving,
  isRejecting,
  onBulkReview,
  onClearSelection,
  onOpenFile,
  onRefresh,
  onReview,
  onSelect,
  openingFileId,
  selectedInvoice,
  similarInvoices,
  similarInvoicesLoading,
}: {
  invoices: InvoiceDetail[];
  isApproving: boolean;
  isRejecting: boolean;
  onBulkReview: (decision: "approve" | "reject", invoices: InvoiceDetail[]) => void;
  onClearSelection: () => void;
  onOpenFile: (file: InvoiceFile) => void;
  onRefresh: () => void;
  onReview: (decision: "approve" | "reject", formData: FormData) => void;
  onSelect: (invoiceId: string) => void;
  openingFileId: string | null;
  selectedInvoice: InvoiceDetail | null;
  similarInvoices: SimilarInvoice[];
  similarInvoicesLoading: boolean;
}) {
  const reviewFormRef = useRef<HTMLFormElement>(null);
  const [confirmRejectOpen, setConfirmRejectOpen] = useState(false);
  const [pendingBulkReject, setPendingBulkReject] = useState<InvoiceDetail[] | null>(null);

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
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Invoices</h2>
            <Button aria-label="Refresh invoices" onClick={onRefresh} size="icon" title="Refresh invoices" type="button" variant="outline">
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
          <div className="mt-4">
            <DataTable
              bulkActions={[
                { label: "Approve", icon: CheckCircle2, onClick: (rows) => onBulkReview("approve", rows) },
                { label: "Reject", icon: XCircle, onClick: (rows) => setPendingBulkReject(rows), variant: "destructive" },
              ]}
              columns={invoiceColumns}
              data={invoices}
              emptyMessage="No invoices loaded."
              enableColumnVisibility
              enableExport={{ filename: "invoices.csv" }}
              enableRowSelection
              getRowId={(invoice) => invoice.invoice_id}
            />
            {selectedInvoice ? (
              <p className="mt-3 text-xs text-muted-foreground">Selected invoice: {selectedInvoice.invoice_number}</p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {!selectedInvoice ? (
        <EmptyPanel title="Select an invoice to review." />
      ) : (
        <Card>
          <CardHeader>
            <nav aria-label="Breadcrumb" className="mb-1 flex items-center gap-1.5 text-xs text-muted-foreground">
              <button className="hover:text-foreground hover:underline" onClick={onClearSelection} type="button">
                Review Queue
              </button>
              <span aria-hidden="true">/</span>
              <span aria-current="page">{selectedInvoice.invoice_number}</span>
            </nav>
            <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
              <div>
                <CardTitle className="text-xl">{selectedInvoice.invoice_number}</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  {selectedInvoice.currency} {selectedInvoice.total_amount || "0.00"} · {selectedInvoice.status}
                </p>
              </div>
              <StatusPill label={selectedInvoice.status} tone={selectedInvoice.status === "approved" ? "ok" : selectedInvoice.status === "failed" ? "error" : "info"} />
            </div>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-4 md:grid-cols-2"
              onSubmit={(event) => {
                // Only Approve submits natively now; Reject is diverted to a confirmation
                // dialog (below) whose onConfirm reads this same form's FormData directly.
                event.preventDefault();
                onReview("approve", new FormData(event.currentTarget));
              }}
              ref={reviewFormRef}
            >
              {/* Prefilled with the extracted values so reviewers edit-in-place to correct them. */}
              <Field label="Invoice number" name="invoice_number" defaultValue={selectedInvoice.invoice_number} />
              <Field label="Invoice date" name="invoice_date" type="date" defaultValue={selectedInvoice.invoice_date || ""} />
              <Field label="Total amount" name="total_amount" type="number" step="0.01" defaultValue={selectedInvoice.total_amount || ""} />
              <Field label="Currency" name="currency" defaultValue={selectedInvoice.currency} />
              <div className="grid gap-1.5 md:col-span-2">
                <Label htmlFor="notes">Review notes</Label>
                <Textarea id="notes" name="notes" rows={3} placeholder="Decision notes" />
              </div>
              <div className="flex flex-wrap gap-2 md:col-span-2">
                <Button disabled={isApproving} type="submit">
                  <CheckCircle2 className="h-4 w-4" />
                  Approve
                </Button>
                <Button
                  disabled={isRejecting}
                  onClick={() => setConfirmRejectOpen(true)}
                  type="button"
                  variant="destructive"
                >
                  <XCircle className="h-4 w-4" />
                  Reject
                </Button>
              </div>
            </form>

            <DetailSections
              invoice={selectedInvoice}
              onOpenFile={onOpenFile}
              onSelect={onSelect}
              openingFileId={openingFileId}
              similarInvoices={similarInvoices}
              similarInvoicesLoading={similarInvoicesLoading}
            />
          </CardContent>
        </Card>
      )}

      <ConfirmDialog
        confirmLabel="Reject invoice"
        description={`This will reject "${selectedInvoice?.invoice_number}" and record the decision in the audit log. This cannot be undone.`}
        onConfirm={() => {
          setConfirmRejectOpen(false);
          if (reviewFormRef.current) onReview("reject", new FormData(reviewFormRef.current));
        }}
        onOpenChange={setConfirmRejectOpen}
        open={confirmRejectOpen}
        title="Reject this invoice?"
      />

      <ConfirmDialog
        confirmLabel={`Reject ${pendingBulkReject?.length ?? 0} invoice${pendingBulkReject?.length === 1 ? "" : "s"}`}
        description="This will reject every selected invoice and record each decision in the audit log. This cannot be undone."
        onConfirm={() => {
          if (pendingBulkReject) onBulkReview("reject", pendingBulkReject);
          setPendingBulkReject(null);
        }}
        onOpenChange={(open) => !open && setPendingBulkReject(null)}
        open={pendingBulkReject !== null}
        title="Reject selected invoices?"
      />
    </section>
  );
}

// Similarity at or above this reads as "probably the same invoice submitted
// twice" — worth flagging to the reviewer, not just ranking.
const DUPLICATE_SIMILARITY_THRESHOLD = 0.95;

function DetailSections({
  invoice,
  onOpenFile,
  onSelect,
  openingFileId,
  similarInvoices,
  similarInvoicesLoading,
}: {
  invoice: InvoiceDetail;
  onOpenFile: (file: InvoiceFile) => void;
  onSelect: (invoiceId: string) => void;
  openingFileId: string | null;
  similarInvoices: SimilarInvoice[];
  similarInvoicesLoading: boolean;
}) {
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
              {openingFileId === file.file_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
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
      {/* Nearest invoices by embedding similarity (pgvector) — context for the
          reviewer plus a near-duplicate flag beyond the exact checksum guard. */}
      <DataBlock title="Similar invoices">
        {similarInvoicesLoading ? <p className="text-sm text-muted-foreground">Searching…</p> : null}
        {!similarInvoicesLoading && similarInvoices.length === 0 ? (
          <p className="text-sm text-muted-foreground">No similar invoices yet — available once extraction completes.</p>
        ) : null}
        {similarInvoices.map((similar) => (
          <button className="list-row" key={similar.invoice_id} onClick={() => onSelect(similar.invoice_id)} type="button">
            <span className="flex items-center gap-2">
              <span className="font-medium text-primary">{similar.invoice_number}</span>
              <span className="text-muted-foreground">
                {similar.currency} {similar.total_amount || "0.00"}
              </span>
              {similar.similarity >= DUPLICATE_SIMILARITY_THRESHOLD ? (
                <StatusPill label="possible duplicate" tone="error" />
              ) : null}
            </span>
            <span className="text-muted-foreground">{Math.round(similar.similarity * 100)}% match</span>
          </button>
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
