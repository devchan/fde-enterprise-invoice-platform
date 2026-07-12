import type { ApiError, Session } from "../domain/types";

export class SessionExpiredError extends Error {
  constructor() {
    super("session_expired");
  }
}

const REFRESH_PATH = "/api/v1/auth/refresh";

export class ApiClient {
  constructor(private readonly baseUrl: string) {}

  async request<T>(path: string, init: RequestInit = {}, session: Session | null = null): Promise<T> {
    return this.send<T>(path, init, session, true);
  }

  private async send<T>(path: string, init: RequestInit, session: Session | null, allowRefresh: boolean): Promise<T> {
    const headers = new Headers(init.headers);
    if (!(init.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    headers.set("X-Request-ID", crypto.randomUUID());

    // credentials: "include" sends the httpOnly auth cookies; the token is never
    // read by JavaScript, which removes the XSS token-exfiltration risk.
    const response = await fetch(`${this.baseUrl}${path}`, { ...init, headers, credentials: "include" });

    if (!response.ok) {
      if (response.status === 401 && session && allowRefresh && !path.startsWith("/api/v1/auth/")) {
        // Access token likely expired: attempt a single silent refresh, then retry.
        const refreshed = await fetch(`${this.baseUrl}${REFRESH_PATH}`, { method: "POST", credentials: "include" });
        if (refreshed.ok) {
          return this.send<T>(path, init, session, false);
        }
      }
      let payload: ApiError = {};
      try {
        payload = (await response.json()) as ApiError;
      } catch {
        payload = {};
      }
      if (response.status === 401 && session) {
        throw new SessionExpiredError();
      }
      const message = payload.error?.message || `${response.status} ${response.statusText}`;
      throw new Error(`${payload.error?.code || "api_error"}: ${message}`);
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }
}
