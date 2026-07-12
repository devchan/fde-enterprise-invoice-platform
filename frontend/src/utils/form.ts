export function emptyToUndefined(value: FormDataEntryValue | null): string | undefined {
  const normalized = String(value || "").trim();
  return normalized || undefined;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed.";
}
