import { useId, type InputHTMLAttributes } from "react";
import { Input } from "../ui/input";
import { Label } from "../ui/label";

// Labeled input wrapper. Everything except `label`/`error` is spread straight onto
// <input>, so native attributes and react-hook-form's register() props pass through
// unchanged. When `error` is set, aria-invalid/aria-describedby associate it with the
// input for screen readers (rather than callers rendering a disconnected sibling <p>).
export function Field({
  error,
  label,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { error?: string; label: string }) {
  const id = useId();
  const errorId = `${id}-error`;
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input aria-describedby={error ? errorId : undefined} aria-invalid={Boolean(error)} id={id} {...props} />
      {error ? (
        <p className="field-error" id={errorId} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
