import { useState } from "react";
import { HelpCircle, Loader2, MessageSquareText, Sparkles } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import type { AssistantAskResponse, InvoiceDetail } from "../../domain/types";

// Ask-box for the read-only AP assistant. Questions are submitted (never
// per-keystroke) because the server may run an LLM tool-calling loop that
// takes several seconds; the answer arrives with the tool trace so reviewers
// can see exactly which data it was grounded in.
export function AssistantPanel({
  isAsking,
  latest,
  onAsk,
  selectedInvoice,
}: {
  isAsking: boolean;
  latest: AssistantAskResponse | null;
  onAsk: (question: string) => void;
  selectedInvoice: InvoiceDetail | null;
}) {
  const [question, setQuestion] = useState("");

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center gap-2">
          <MessageSquareText className="h-4 w-4 text-primary" aria-hidden="true" />
          <h2 className="text-base font-semibold tracking-tight">Assistant</h2>
          <span className="eyebrow ml-auto">AI · read-only</span>
        </div>
        <form
          className="mt-4 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (question.trim()) onAsk(question.trim());
          }}
        >
          <Input
            aria-label="Ask the assistant about your invoices"
            maxLength={2000}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder='Ask: "what failed today?"'
            value={question}
          />
          <Button aria-label="Ask assistant" disabled={isAsking || !question.trim()} size="icon" title="Ask assistant" type="submit" variant="outline">
            {isAsking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          </Button>
        </form>
        {/* One-click diagnosis for the invoice being reviewed; the UUID in the
            question is what both the LLM and the keyless fallback key off. */}
        {selectedInvoice ? (
          <Button
            className="mt-2"
            disabled={isAsking}
            onClick={() => onAsk(`why is invoice ${selectedInvoice.invoice_id} stuck?`)}
            size="sm"
            type="button"
            variant="ghost"
          >
            <HelpCircle className="h-4 w-4" />
            Why is {selectedInvoice.invoice_number} stuck?
          </Button>
        ) : null}
        {isAsking ? <p className="mt-3 text-sm text-muted-foreground">Checking your invoices…</p> : null}
        {!isAsking && latest ? (
          <div className="mt-3 space-y-2" data-testid="assistant-answer">
            <p className="text-xs text-muted-foreground">Q: {latest.question}</p>
            {/* whitespace-pre-line: the fallback answerer formats multi-line lists.
                Amber left rule = the shared "AI produced this" signal. */}
            <p className="whitespace-pre-line rounded-md border border-border border-l-2 border-l-primary/60 bg-muted/60 p-3 text-sm">
              {latest.answer}
            </p>
            <div className="flex flex-wrap items-center gap-1.5">
              {latest.tool_calls.map((call, index) => (
                <Badge key={`${call.tool}-${index}`} title={JSON.stringify(call.arguments)} variant="ai">
                  {call.tool}
                </Badge>
              ))}
              <span className="font-mono text-[11px] text-muted-foreground">{latest.model_name}</span>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
