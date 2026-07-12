import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { queryClient } from "./app/query-client";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import "./styles.css";

// Provider order matters: ErrorBoundary is outermost so it can catch failures from
// anything below it, including the query provider and the app itself.
createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
);
