import { useId, type InputHTMLAttributes } from "react";
import { Input } from "../ui/input";
import { Label } from "../ui/label";

// Labeled input wrapper. Everything except `label` is spread straight onto <input>,
// so native attributes and react-hook-form's register() props pass through unchanged.
export function Field({ label, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  const id = useId();
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} {...props} />
    </div>
  );
}
