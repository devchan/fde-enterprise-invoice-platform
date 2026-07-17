import { useEffect, useRef, useState } from "react";
import { HelpCircle, Loader2, MessageSquareText, Sparkles, Trash2, X } from "lucide-react";
import type { AssistantInvoiceContext } from "../../app/AssistantContext";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import type { AssistantAskResponse, AssistantToolCall } from "../../domain/types";

// One turn in the conversation. User turns carry only their text; assistant
// turns carry the grounded answer plus the tool trace and model that produced
// it, so every reply stays traceable to the data it came from.
type ChatMessage =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; answer: string; toolCalls: AssistantToolCall[]; modelName: string };

// Starter questions shown on the empty thread so a reviewer who has never used
// the assistant sees what it can answer instead of a blank box.
const SUGGESTED_PROMPTS = [
  "What failed today?",
  "How accurate is extraction lately?",
  "Show invoices that need review",
];

// Chat-style panel for the read-only AP assistant. The backend answers each
// question independently (no server-side memory); the running thread lives here
// so the reviewer can read a question against its answer and its tool trace.
// Questions submit on Enter/click (never per-keystroke) because the server may
// run an LLM tool-calling loop that takes several seconds.
export function AssistantPanel({
  className,
  isAsking,
  latest,
  onAsk,
  onClose,
  selectedInvoice,
}: {
  className?: string;
  isAsking: boolean;
  latest: AssistantAskResponse | null;
  onAsk: (question: string) => void;
  // When set, the header shows a close control — the panel is a dismissible
  // floating window rather than an always-present card.
  onClose?: () => void;
  selectedInvoice: AssistantInvoiceContext | null;
}) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // Monotonic key source (no Math.random, stable across re-renders).
  const nextId = useRef(0);
  // The last response object we appended, so a re-render with the same mutation
  // data doesn't duplicate the assistant turn.
  const appendedResponse = useRef<AssistantAskResponse | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  function ask(raw: string) {
    const text = raw.trim();
    if (!text || isAsking) return;
    setMessages((prev) => [...prev, { id: (nextId.current += 1), role: "user", text }]);
    onAsk(text);
    setQuestion("");
  }

  // Fold each new server answer into the thread as an assistant turn. Keyed off
  // object identity: React Query hands back a fresh object per question, so this
  // fires exactly once per answer even under StrictMode's double-invoke.
  useEffect(() => {
    if (latest && latest !== appendedResponse.current) {
      appendedResponse.current = latest;
      setMessages((prev) => [
        ...prev,
        { id: (nextId.current += 1), role: "assistant", answer: latest.answer, toolCalls: latest.tool_calls, modelName: latest.model_name },
      ]);
    }
  }, [latest]);

  // Keep the newest turn (and the thinking indicator) in view as the thread grows.
  useEffect(() => {
    const thread = threadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [messages, isAsking]);

  const hasThread = messages.length > 0;
  const stuckQuestion = selectedInvoice ? `why is invoice ${selectedInvoice.invoice_id} stuck?` : null;

  return (
    <Card className={className}>
      <CardContent className="pt-6">
        <div className="flex items-center gap-2">
          <MessageSquareText className="h-4 w-4 text-primary" aria-hidden="true" />
          <h2 className="text-base font-semibold tracking-tight">Assistant</h2>
          <span className="eyebrow ml-auto">AI · read-only</span>
          {hasThread ? (
            <Button
              aria-label="Clear conversation"
              className="h-7 w-7"
              onClick={() => {
                setMessages([]);
                appendedResponse.current = latest;
              }}
              size="icon"
              title="Clear conversation"
              type="button"
              variant="ghost"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          ) : null}
          {onClose ? (
            <Button
              aria-label="Close assistant"
              className="h-7 w-7"
              onClick={onClose}
              size="icon"
              title="Close assistant"
              type="button"
              variant="ghost"
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          ) : null}
        </div>

        {/* Conversation thread. Empty state doubles as onboarding: what the
            assistant is, plus tap-to-ask starter prompts. */}
        <div
          className="mt-4 max-h-80 space-y-3 overflow-y-auto pr-1"
          ref={threadRef}
          aria-live="polite"
          aria-label="Assistant conversation"
        >
          {!hasThread && !isAsking ? (
            <div className="rounded-md border border-dashed border-border bg-muted/40 p-4 text-center">
              <p className="text-sm font-medium">Ask about your invoices</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Grounded in your data, read-only. Every answer shows the tools it used.
              </p>
              <div className="mt-3 flex flex-wrap justify-center gap-1.5">
                {SUGGESTED_PROMPTS.map((prompt) => (
                  <button
                    className="rounded-full border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                    key={prompt}
                    onClick={() => ask(prompt)}
                    type="button"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {messages.map((message) =>
            message.role === "user" ? (
              <div className="flex justify-end" key={message.id}>
                <p className="max-w-[85%] rounded-lg rounded-br-sm border border-primary/25 bg-primary/10 px-3 py-2 text-sm">
                  {message.text}
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-1.5" key={message.id}>
                {/* Amber left rule = the shared "AI produced this" signal.
                    whitespace-pre-line preserves the fallback answerer's lists. */}
                <p className="max-w-[90%] whitespace-pre-line rounded-lg rounded-bl-sm border border-border border-l-2 border-l-primary/60 bg-muted/60 px-3 py-2 text-sm">
                  {message.answer}
                </p>
                <div className="flex flex-wrap items-center gap-1.5 pl-0.5">
                  {message.toolCalls.map((call, index) => (
                    <Badge key={`${call.tool}-${index}`} title={JSON.stringify(call.arguments)} variant="ai">
                      {call.tool}
                    </Badge>
                  ))}
                  <span className="font-mono text-[11px] text-muted-foreground">{message.modelName}</span>
                </div>
              </div>
            ),
          )}

          {isAsking ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              Checking your invoices…
            </div>
          ) : null}
        </div>

        {/* One-click diagnosis for the invoice being reviewed; the UUID in the
            question is what both the LLM and the keyless fallback key off. */}
        {stuckQuestion ? (
          <Button className="mt-3" disabled={isAsking} onClick={() => ask(stuckQuestion)} size="sm" type="button" variant="ghost">
            <HelpCircle className="h-4 w-4" />
            Why is {selectedInvoice?.invoice_number} stuck?
          </Button>
        ) : null}

        <form
          className="mt-3 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            ask(question);
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
      </CardContent>
    </Card>
  );
}
