import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { queryClient } from "./app/query-client";
import { router } from "./app/router";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { ThemeProvider } from "./components/common/theme-provider";
import "./styles.css";

// Provider order matters: ErrorBoundary is outermost so it can catch failures from
// anything below it, including the query provider and the router.
createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <ErrorBoundary>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>,
);
