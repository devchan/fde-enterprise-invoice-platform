import { afterEach, describe, expect, it, vi } from "vitest";
import type { Session } from "../domain/types";
import { ApiClient, SessionExpiredError } from "./api-client";

const session: Session = {
  user_id: "u1",
  organization_id: "o1",
  email: "user@example.com",
  role: "admin",
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ApiClient", () => {
  it("sends cookies (credentials: include) and never an Authorization header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    await client.request("/api/v1/invoices", { method: "GET" }, session);

    const [, init] = fetchMock.mock.calls[0];
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).has("Authorization")).toBe(false);
    expect(new Headers(init.headers).has("X-Request-ID")).toBe(true);
  });

  it("silently refreshes once on 401 and retries the original request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: "authentication_required" } }))
      .mockResolvedValueOnce(jsonResponse(200, {})) // /auth/refresh
      .mockResolvedValueOnce(jsonResponse(200, { invoices: [] })); // retried call
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    const result = await client.request<{ invoices: unknown[] }>("/api/v1/invoices", { method: "GET" }, session);

    expect(result).toEqual({ invoices: [] });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toContain("/api/v1/auth/refresh");
  });

  it("throws SessionExpiredError when refresh also fails", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: "authentication_required" } }))
      .mockResolvedValueOnce(jsonResponse(401, {})) // /auth/refresh fails
      .mockResolvedValueOnce(jsonResponse(401, {})); // retried call still 401
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    await expect(client.request("/api/v1/invoices", { method: "GET" }, session)).rejects.toBeInstanceOf(
      SessionExpiredError,
    );
  });

  it("does not attempt refresh for auth endpoints", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(401, { error: { code: "invalid_credentials" } }));
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    await expect(client.request("/api/v1/auth/me", { method: "GET" }, null)).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
