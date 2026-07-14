import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, ShieldCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Field } from "../../components/common/Field";
import { Button } from "../../components/ui/button";
import type { LoginCredentials } from "../../domain/types";

// Client-side validation for immediate feedback; the server still authoritatively
// validates credentials. Only checks shape here (valid email, non-empty password).
const signInSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});

export function SignInForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (credentials: LoginCredentials) => void;
}) {
  const {
    formState: { errors },
    handleSubmit,
    register,
  } = useForm<LoginCredentials>({
    resolver: zodResolver(signInSchema),
    defaultValues: { email: "", password: "" },
  });

  return (
    <form className="mt-5 space-y-3 border-t border-border pt-5" onSubmit={handleSubmit(onSubmit)}>
      <Field
        error={errors.email?.message}
        label="Email"
        placeholder="admin@example.com"
        type="email"
        required
        {...register("email")}
      />
      <Field
        error={errors.password?.message}
        label="Password"
        placeholder="Password"
        type="password"
        required
        {...register("password")}
      />
      <Button className="w-full" disabled={busy} type="submit">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
        Sign in
      </Button>
    </form>
  );
}
