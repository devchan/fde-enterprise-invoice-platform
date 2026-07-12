import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Catches render/runtime errors anywhere in the component tree so an
 * unhandled throw degrades to a recoverable message instead of a blank screen.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface the failure for local debugging and any attached log drain.
    console.error("Unhandled UI error:", error, info.componentStack);
  }

  private handleReload = (): void => {
    this.setState({ error: null });
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div role="alert" className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
          <h1 className="text-lg font-semibold">Something went wrong</h1>
          <p className="max-w-md text-sm text-muted-foreground">
            The application hit an unexpected error. Reloading usually resolves it. If the problem persists, contact
            your administrator.
          </p>
          <button
            type="button"
            onClick={this.handleReload}
            className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-muted"
          >
            Reload
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
