import { MessageSquareText } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAssistant } from "../../app/AssistantContext";
import type { Session } from "../../domain/types";
import { useAskAssistantMutation } from "../../queries/assistant";
import { Button } from "../../components/ui/button";
import { AssistantPanel } from "./AssistantPanel";

// Global floating assistant: a launcher pinned to the corner of every screen
// plus the chat window it opens. Mounted once in the app shell so the
// conversation and its in-flight request persist across route changes, and the
// panel stays mounted (only hidden) while closed so reopening keeps the thread.
export function AssistantWidget({ session }: { session: Session }) {
  const { open, setOpen, contextInvoice } = useAssistant();
  const askAssistantMutation = useAskAssistantMutation(session);

  return (
    <>
      {!open ? (
        <Button
          aria-label="Open assistant"
          className="fixed bottom-5 right-5 z-40 h-12 w-12 rounded-full p-0 shadow-lg"
          onClick={() => setOpen(true)}
          title="Ask the assistant"
          type="button"
        >
          <MessageSquareText className="h-5 w-5" />
        </Button>
      ) : null}
      <div
        className={cn(
          "fixed bottom-5 right-5 z-40 w-[380px] max-w-[calc(100vw-2.5rem)]",
          open ? "block" : "hidden",
        )}
      >
        <AssistantPanel
          className="shadow-2xl"
          isAsking={askAssistantMutation.isPending}
          latest={askAssistantMutation.data ?? null}
          onAsk={(question) => askAssistantMutation.mutate(question)}
          onClose={() => setOpen(false)}
          selectedInvoice={contextInvoice}
        />
      </div>
    </>
  );
}
