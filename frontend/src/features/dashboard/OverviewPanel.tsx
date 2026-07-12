import { RefreshCw, ShieldCheck } from "lucide-react";
import { LoadingPanel, SignInRequiredPanel } from "../../components/common/AccessPanels";

export function OverviewPanel({
  loading,
  signedIn,
  stats,
  refresh,
  checkHealth,
}: {
  loading: boolean;
  signedIn: boolean;
  stats: Array<{ label: string; value: string }>;
  refresh: () => void;
  checkHealth: () => void;
}) {
  return (
    <>
      <section className="panel">
        <div>
          <p className="text-sm font-medium text-primary">Operations cockpit</p>
          <h2 className="mt-1 text-xl font-semibold">Enterprise invoice review</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            This React frontend is connected to the FastAPI backend and covers the first operational workflows:
            upload, review, recovery, audit, and user administration.
          </p>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="btn-secondary" onClick={refresh} type="button">
            <RefreshCw className="h-4 w-4" />
            Refresh data
          </button>
          <button className="btn-secondary" onClick={checkHealth} type="button">
            <ShieldCheck className="h-4 w-4" />
            Check API
          </button>
        </div>
      </section>
      {signedIn && loading ? (
        <LoadingPanel title="Loading operational data." />
      ) : signedIn ? (
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {stats.map((stat) => (
            <article className="panel" key={stat.label}>
              <p className="text-sm text-muted-foreground">{stat.label}</p>
              <p className="mt-2 text-3xl font-semibold">{stat.value}</p>
            </article>
          ))}
        </section>
      ) : (
        <SignInRequiredPanel title="Sign in to load operational data." />
      )}
    </>
  );
}
