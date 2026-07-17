import type { AssistantAskResponse, Session } from "../domain/types";
import type { ApiClient } from "./api-client";

export class AssistantService {
  constructor(private readonly apiClient: ApiClient) {}

  // The agent runs server-side as the authenticated user (read-only tools,
  // tenant-scoped), so the client only ships the question and renders the
  // answer plus its tool trace.
  ask(session: Session, question: string): Promise<AssistantAskResponse> {
    return this.apiClient.request<AssistantAskResponse>(
      "/api/v1/assistant/ask",
      { method: "POST", body: JSON.stringify({ question }) },
      session,
    );
  }
}
