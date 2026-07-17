import { useRef, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { CheckCircle2, Download, Loader2, RefreshCw, Sparkles, X, XCircle } from "lucide-react";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { DataBlock } from "../../components/common/DataBlock";
import { DataTable } from "../../components/common/DataTable";
import { EmptyPanel } from "../../components/common/EmptyPanel";
import { Field } from "../../components/common/Field";
import { StatusPill } from "../../components/common/StatusPill";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import type { AssistantAskResponse, FieldConfidences, InvoiceDetail, InvoiceFile, SimilarInvoice } from "../../domain/types";
import { formatDate } from "../../utils/format";
import { AssistantPanel } from "./AssistantPanel";

// Below this per-field extraction confidence the review form highlights the
// field so the reviewer verifies it against the document (matches the server's
// field_confidence_low threshold).
const FIELD_CONFIDENCE_WARN_THRESHOLD = 0.75;

// Rule codes produced by post-extraction anomaly detection (not document
// validation); rendered with a distinct badge so reviewers read them as fraud/
// duplicate signals rather than data errors.
const ANOMALY_RULE_CODES = new Set(["amount_anomaly", "near_duplicate_similarity"]);

// Pull the extractor's per-field confidences out of the raw payload. Defensive:
// older extractions (or non-object payloads) simply yield no highlights.
function fieldConfidences(invoice: InvoiceDetail): FieldConfidences {
  const payload = invoice.latest_extraction?.extracted_payload;
  const confidences = payload && typeof payload === "object" ? (payload as Record<string, unknown>).field_confidences : null;
  return confidences && typeof confidences === "object" ? (confidences as FieldConfidences) : {};
}

function confidenceWarning(confidences: FieldConfidences, field: keyof FieldConfidences): string | undefined {
  const raw = confidences[field];
  if (raw == null) return undefined;
  const value = Number(raw);
  if (Number.isNaN(value) || value >= FIELD_CONFIDENCE_WARN_THRESHOLD) return undefined;
  return `AI confidence ${Math.round(value * 100)}% — verify against document`;
}

export function ReviewPanel({
  aiFilters,
  aiSearchActive,
  assistantAnswer,
  invoices,
  isAiSearching,
  isApproving,
  isAsking,
  isRejecting,
  onAiSearch,
  onAsk,
  onBulkReview,
  onClearAiSearch,
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
  aiFilters: Record<string, unknown> | null;
  aiSearchActive: boolean;
  assistantAnswer: AssistantAskResponse | null;
  invoices: InvoiceDetail[];
  isAiSearching: boolean;
  isApproving: boolean;
  isAsking: boolean;
  isRejecting: boolean;
  onAiSearch: (query: string) => void;
  onAsk: (question: string) => void;
  onBulkReview: (decision: "approve" | "reject", invoices: InvoiceDetail[]) => void;
  onClearAiSearch: () => void;
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
  const [aiQuery, setAiQuery] = useState("");

  // Defined inside the component so the invoice-number cell can close over onSelect.
  const invoiceColumns: ColumnDef<InvoiceDetail>[] = [
    {
      accessorKey: "invoice_number",
      header: "Invoice",
      cell: ({ row }) => (
        <button
          className="num font-medium text-primary underline-offset-2 hover:underline"
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
      cell: ({ row }) => <StatusPill label={row.original.status} />,
    },
    {
      accessorKey: "created_at",
      header: "Created",
      cell: ({ row }) => <span className="num text-xs text-muted-foreground">{formatDate(row.original.created_at)}</span>,
    },
  ];

  return (
    <section className="grid gap-4 xl:grid-cols-[360px_1fr]">
      {/* Left rail: the invoice list plus the assistant ask-box, stacked so the
          assistant stays reachable while browsing or reviewing. */}
      <div className="space-y-4">
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Invoices</h2>
            <Button aria-label="Refresh invoices" onClick={onRefresh} size="icon" title="Refresh invoices" type="button" variant="outline">
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
          {/* Natural-language search: submitted (never per-keystroke) because the
              server may consult an LLM to interpret the query. */}
          <form
            className="mt-4 flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (aiQuery.trim()) onAiSearch(aiQuery.trim());
            }}
          >
            <Input
              aria-label="Ask AI to search invoices"
              onChange={(event) => setAiQuery(event.target.value)}
              placeholder='Ask AI: "approved acme invoices over $10k from june"'
              value={aiQuery}
            />
            <Button aria-label="Search with AI" disabled={isAiSearching || !aiQuery.trim()} size="icon" title="Search with AI" type="submit" variant="outline">
              {isAiSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            </Button>
          </form>
          {aiSearchActive ? (
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <span>Interpreted as:</span>
              {aiFilters && Object.keys(aiFilters).length > 0 ? (
                Object.entries(aiFilters).map(([key, value]) => (
                  <Badge key={key} variant="ai">
                    {key}={String(value)}
                  </Badge>
                ))
              ) : (
                <Badge variant="ai">no filters</Badge>
              )}
              <button
                className="inline-flex items-center gap-1 text-primary hover:underline"
                onClick={() => {
                  setAiQuery("");
                  onClearAiSearch();
                }}
                type="button"
              >
                <X className="h-3 w-3" />
                Clear
              </button>
            </div>
          ) : null}
          <div className="mt-4">
            <DataTable
              bulkActions={[
                { label: "Approve", icon: CheckCircle2, onClick: (rows) => onBulkReview("approve", rows) },
                { label: "Reject", icon: XCircle, onClick: (rows) => setPendingBulkReject(rows), variant: "destructive" },
              ]}
              columns={invoiceColumns}
              data={invoices}
              emptyMessage="No invoices yet — upload one to start the pipeline."
              enableColumnVisibility
              enableExport={{ filename: "invoices.csv" }}
              enableRowSelection
              // Narrow left-rail list: size to the column, don't force a scrollbar.
              fitContainer
              getRowId={(invoice) => invoice.invoice_id}
            />
            {selectedInvoice ? (
              <p className="mt-3 text-xs text-muted-foreground">Selected invoice: {selectedInvoice.invoice_number}</p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <AssistantPanel
        isAsking={isAsking}
        latest={assistantAnswer}
        onAsk={onAsk}
        selectedInvoice={selectedInvoice}
      />
      </div>

      {!selectedInvoice ? (
        <EmptyPanel
          hint="Pick an invoice from the list to see its extracted fields, validation results, and similar invoices."
          title="No invoice selected"
        />
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
                <CardTitle className="num text-xl tracking-tight">{selectedInvoice.invoice_number}</CardTitle>
                <p className="num mt-1 text-sm text-muted-foreground">
                  {selectedInvoice.currency} {selectedInvoice.total_amount || "0.00"}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {/* An approved invoice with no review rows can only have been
                    approved by the confidence-gated auto-approval step. */}
                {selectedInvoice.status === "approved" && selectedInvoice.reviews.length === 0 ? (
                  <Badge variant="ai">
                    <Sparkles className="mr-1 h-3 w-3" />
                    Auto-approved by AI
                  </Badge>
                ) : null}
                <StatusPill label={selectedInvoice.status} />
              </div>
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
              {/* Prefilled with the extracted values so reviewers edit-in-place to correct
                  them; fields the extractor was unsure about get an amber warning. */}
              <Field
                defaultValue={selectedInvoice.invoice_number}
                label="Invoice number"
                name="invoice_number"
                warning={confidenceWarning(fieldConfidences(selectedInvoice), "invoice_number")}
              />
              <Field
                defaultValue={selectedInvoice.invoice_date || ""}
                label="Invoice date"
                name="invoice_date"
                type="date"
                warning={confidenceWarning(fieldConfidences(selectedInvoice), "invoice_date")}
              />
              <Field
                defaultValue={selectedInvoice.total_amount || ""}
                label="Total amount"
                name="total_amount"
                step="0.01"
                type="number"
                warning={confidenceWarning(fieldConfidences(selectedInvoice), "total_amount")}
              />
              <Field
                defaultValue={selectedInvoice.currency}
                label="Currency"
                name="currency"
                warning={confidenceWarning(fieldConfidences(selectedInvoice), "currency")}
              />
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
          <div className="py-1" key={result.validation_result_id}>
            <div className="list-row">
              <span className="flex items-center gap-2 font-mono text-xs">
                {result.rule_code}
                {ANOMALY_RULE_CODES.has(result.rule_code) ? <StatusPill label="anomaly" tone="accent" /> : null}
              </span>
              <span className={`font-mono text-xs ${result.passed ? "text-good" : result.severity === "warning" ? "text-warn" : "text-crit"}`}>
                {result.passed ? "passed" : result.severity}
              </span>
            </div>
            {/* AI/template-written reviewer guidance, present only on failed rules. */}
            {!result.passed && result.explanation ? (
              <p className="mt-0.5 text-xs text-muted-foreground">{result.explanation}</p>
            ) : null}
            {!result.passed && result.suggested_fix ? (
              <p className="mt-0.5 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">Fix:</span> {result.suggested_fix}
              </p>
            ) : null}
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
            <span className="flex items-center gap-2">
              {item.description}
              {/* AI-assigned expense category; absent for legacy rows or when the model was unsure. */}
              {item.category ? <Badge variant="ai">{item.category.replace(/_/g, " ")}</Badge> : null}
            </span>
            <span className="num">{item.line_total || "—"}</span>
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
              <span className="num font-medium text-primary">{similar.invoice_number}</span>
              <span className="num text-muted-foreground">
                {similar.currency} {similar.total_amount || "0.00"}
              </span>
              {similar.similarity >= DUPLICATE_SIMILARITY_THRESHOLD ? (
                <StatusPill label="possible duplicate" tone="accent" />
              ) : null}
            </span>
            <span className="num text-xs text-muted-foreground">{Math.round(similar.similarity * 100)}% match</span>
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
