import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { queryClient } from "./app/query-client";
import { router } from "./app/router";
import { ToastProvider } from "./app/ToastContext";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { ThemeProvider } from "./components/common/theme-provider";
// Fonts ship as npm packages (no CDN): Plex Sans carries UI text, Plex Mono
// carries data (amounts, ids, statuses) and the eyebrow labels.
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "./styles.css";

// Provider order matters: ErrorBoundary is outermost so it can catch failures from
// anything below it. ToastProvider sits inside QueryClientProvider since mutation
// hooks call useToast() to report success/error feedback.
createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <ErrorBoundary>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <ToastProvider>
            <RouterProvider router={router} />
          </ToastProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>,
);
