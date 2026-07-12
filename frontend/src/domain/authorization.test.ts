import { describe, expect, it } from "vitest";
import { canAccessTab, canReview, canUpload, isAdmin } from "./authorization";
import type { Session } from "./types";

const session = (role: string): Session => ({
  user_id: "u1",
  organization_id: "o1",
  email: "user@example.com",
  role,
});

describe("authorization", () => {
  it("recognizes admins", () => {
    expect(isAdmin(session("admin"))).toBe(true);
    expect(isAdmin(session("reviewer"))).toBe(false);
    expect(isAdmin(null)).toBe(false);
  });

  it("grants review to admin and reviewer only", () => {
    expect(canReview(session("admin"))).toBe(true);
    expect(canReview(session("reviewer"))).toBe(true);
    expect(canReview(session("uploader"))).toBe(false);
  });

  it("grants upload to admin and uploader only", () => {
    expect(canUpload(session("admin"))).toBe(true);
    expect(canUpload(session("uploader"))).toBe(true);
    expect(canUpload(session("reviewer"))).toBe(false);
  });

  it("gates tabs by role", () => {
    expect(canAccessTab(null, "overview")).toBe(true);
    expect(canAccessTab(null, "review")).toBe(false);
    expect(canAccessTab(session("reviewer"), "users")).toBe(false);
    expect(canAccessTab(session("admin"), "users")).toBe(true);
    expect(canAccessTab(session("uploader"), "upload")).toBe(true);
    expect(canAccessTab(session("reviewer"), "upload")).toBe(false);
  });
});
