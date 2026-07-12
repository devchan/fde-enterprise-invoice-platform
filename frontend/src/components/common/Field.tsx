import type { InputHTMLAttributes } from "react";

// Labeled input wrapper. Everything except `label` is spread straight onto <input>,
// so native attributes and react-hook-form's register() props pass through unchanged.
export function Field({ label, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input {...props} />
    </label>
  );
}
