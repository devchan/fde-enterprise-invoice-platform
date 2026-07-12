import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom"],
          forms: ["react-hook-form", "@hookform/resolvers", "zod"],
          tanstack: ["@tanstack/react-query", "@tanstack/react-table"],
        },
      },
    },
  },
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 3000,
  },
});
