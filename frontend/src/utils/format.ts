// Truncate long opaque identifiers (UUIDs) for dense table cells; short values pass through.
export function shortId(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

// Render ISO timestamps in the viewer's locale/timezone (undefined = browser default).
export function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
