export function Toast({
  message,
  onClose,
  tone,
}: {
  message: string;
  onClose: () => void;
  tone: "ok" | "error" | "info";
}) {
  // Errors get assertive alert semantics so screen readers interrupt; other tones are polite.
  return (
    <div
      className={`toast toast-${tone}`}
      role={tone === "error" ? "alert" : "status"}
      aria-live={tone === "error" ? "assertive" : "polite"}
    >
      <span>{message}</span>
      <button onClick={onClose} type="button" aria-label="Dismiss notification">
        Dismiss
      </button>
    </div>
  );
}
