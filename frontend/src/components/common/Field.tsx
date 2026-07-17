import { useId, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";
import { Input } from "../ui/input";
import { Label } from "../ui/label";

// Labeled input wrapper. Everything except `label`/`error`/`warning` is spread straight
// onto <input>, so native attributes and react-hook-form's register() props pass through
// unchanged. When `error` is set, aria-invalid/aria-describedby associate it with the
// input for screen readers (rather than callers rendering a disconnected sibling <p>).
// `warning` is a softer signal (e.g. low AI extraction confidence): the value may well
// be fine, so it styles amber and never sets aria-invalid; `error` wins when both are set.
export function Field({
  error,
  label,
  warning,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { error?: string; label: string; warning?: string }) {
  const id = useId();
  const errorId = `${id}-error`;
  const warningId = `${id}-warning`;
  const showWarning = Boolean(warning) && !error;
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        aria-describedby={error ? errorId : showWarning ? warningId : undefined}
        aria-invalid={Boolean(error)}
        className={cn(showWarning && "border-amber-500 focus-visible:ring-amber-500")}
        id={id}
        {...props}
      />
      {error ? (
        <p className="field-error" id={errorId} role="alert">
          {error}
        </p>
      ) : null}
      {showWarning ? (
        <p className="text-xs text-amber-600 dark:text-amber-500" id={warningId}>
          {warning}
        </p>
      ) : null}
    </div>
  );
}
