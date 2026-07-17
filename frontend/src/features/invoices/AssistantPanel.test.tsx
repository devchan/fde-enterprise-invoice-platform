import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AssistantAskResponse } from "../../domain/types";
import { AssistantPanel } from "./AssistantPanel";

const answer: AssistantAskResponse = {
  question: "what failed today?",
  answer: "1 failed processing job(s):\n- invoice abc: provider exploded (attempts: 3)",
  model_name: "assistant-fallback",
  tool_calls: [{ tool: "list_failed_jobs", arguments: { limit: 10 } }],
};

describe("AssistantPanel", () => {
  it("submits a trimmed question and disables Ask while pending", () => {
    const onAsk = vi.fn();
    const { rerender } = render(
      <AssistantPanel isAsking={false} latest={null} onAsk={onAsk} selectedInvoice={null} />,
    );

    fireEvent.change(screen.getByLabelText("Ask the assistant about your invoices"), {
      target: { value: "  what failed today?  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask assistant" }));

    expect(onAsk).toHaveBeenCalledWith("what failed today?");

    rerender(<AssistantPanel isAsking latest={null} onAsk={onAsk} selectedInvoice={null} />);
    expect(screen.getByRole("button", { name: "Ask assistant" })).toBeDisabled();
    expect(screen.getByText("Checking your invoices…")).toBeInTheDocument();
  });

  it("renders the answer with line breaks, tool chips, and model name", () => {
    render(<AssistantPanel isAsking={false} latest={answer} onAsk={vi.fn()} selectedInvoice={null} />);

    // Multi-line fallback answers must keep their list formatting.
    expect(screen.getByText(/1 failed processing job/)).toHaveClass("whitespace-pre-line");
    expect(screen.getByText("list_failed_jobs")).toBeInTheDocument();
    expect(screen.getByText("assistant-fallback")).toBeInTheDocument();
  });

  it("keeps the question and its answer together in the thread", () => {
    const onAsk = vi.fn();
    const { rerender } = render(
      <AssistantPanel isAsking={false} latest={null} onAsk={onAsk} selectedInvoice={null} />,
    );

    fireEvent.change(screen.getByLabelText("Ask the assistant about your invoices"), {
      target: { value: "what failed today?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask assistant" }));

    // The user turn is echoed into the thread immediately, before the answer.
    expect(screen.getByText("what failed today?")).toBeInTheDocument();

    // When the server answer arrives it is folded in as the assistant turn.
    rerender(<AssistantPanel isAsking={false} latest={answer} onAsk={onAsk} selectedInvoice={null} />);
    expect(screen.getByText(/1 failed processing job/)).toBeInTheDocument();
    expect(screen.getByText("what failed today?")).toBeInTheDocument();
  });

  it("offers starter prompts on the empty thread and asks the tapped one", () => {
    const onAsk = vi.fn();
    render(<AssistantPanel isAsking={false} latest={null} onAsk={onAsk} selectedInvoice={null} />);

    fireEvent.click(screen.getByRole("button", { name: "What failed today?" }));
    expect(onAsk).toHaveBeenCalledWith("What failed today?");
  });

  it("clears the conversation back to the empty state", () => {
    render(<AssistantPanel isAsking={false} latest={answer} onAsk={vi.fn()} selectedInvoice={null} />);

    expect(screen.getByText(/1 failed processing job/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear conversation" }));

    expect(screen.queryByText(/1 failed processing job/)).not.toBeInTheDocument();
    expect(screen.getByText("Ask about your invoices")).toBeInTheDocument();
  });

  it("asks the stuck question for the selected invoice via the quick action", () => {
    const onAsk = vi.fn();
    render(
      <AssistantPanel
        isAsking={false}
        latest={null}
        onAsk={onAsk}
        selectedInvoice={
          {
            invoice_id: "42804118-87e3-4f5e-8745-55a68b6a16cf",
            invoice_number: "INV-1",
          } as never
        }
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Why is INV-1 stuck\?/ }));

    // The UUID inside the question is what the backend (LLM and fallback) keys off.
    expect(onAsk).toHaveBeenCalledWith("why is invoice 42804118-87e3-4f5e-8745-55a68b6a16cf stuck?");
  });
});
