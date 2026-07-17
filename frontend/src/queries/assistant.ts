import { useMutation } from "@tanstack/react-query";
import { useToast } from "../app/ToastContext";
import type { Session } from "../domain/types";
import { assistantService } from "../services";
import { errorMessage } from "../utils/form";

// A mutation (never a query): assistant answers are point-in-time and may cost
// LLM tokens server-side, so they must only run on explicit submit and must
// never be cached or refetched automatically.
export function useAskAssistantMutation(session: Session | null) {
  const { setToast } = useToast();

  return useMutation({
    mutationFn: (question: string) => assistantService.ask(session as Session, question),
    onError: (error) => {
      // Surfaces the server's message (e.g. assistant disabled / blank question).
      setToast({ message: errorMessage(error), tone: "error" });
    },
  });
}
