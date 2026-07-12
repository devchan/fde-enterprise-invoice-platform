// Normalize a form field to undefined when blank so it is omitted from JSON payloads
// (the API distinguishes "not provided" from "set to empty").
export function emptyToUndefined(value: FormDataEntryValue | null): string | undefined {
  const normalized = String(value || "").trim();
  return normalized || undefined;
}

// Safely extract a user-facing message from an unknown thrown value.
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed.";
}
