import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Kept separate from vite.config.ts (and out of tsconfig's typecheck scope) so
// the vitest/vite type surface never collides with the app build config.
export default defineConfig({
  plugins: [react()],
  resolve: {
    // Mirrors vite.config.ts so components importing "@/lib/utils" (shadcn/ui)
    // resolve identically under test.
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
