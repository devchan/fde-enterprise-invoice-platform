import { RefreshCw, ShieldCheck } from "lucide-react";
import { SignInRequiredPanel } from "../../components/common/AccessPanels";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Skeleton } from "../../components/ui/skeleton";

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
      <Card>
        <CardContent className="pt-6">
          <div>
            <p className="text-sm font-medium text-primary">Operations cockpit</p>
            <h2 className="mt-1 text-xl font-semibold">Enterprise invoice review</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              This React frontend is connected to the FastAPI backend and covers the first operational workflows:
              upload, review, recovery, audit, and user administration.
            </p>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button onClick={refresh} type="button" variant="outline">
              <RefreshCw className="h-4 w-4" />
              Refresh data
            </Button>
            <Button onClick={checkHealth} type="button" variant="outline">
              <ShieldCheck className="h-4 w-4" />
              Check API
            </Button>
          </div>
        </CardContent>
      </Card>
      {/* Three states: signed-in + loading, signed-in + ready (stat cards), or signed-out prompt. */}
      {signedIn && loading ? (
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, index) => (
            <Card key={index}>
              <CardContent className="space-y-2 pt-6">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-8 w-16" />
              </CardContent>
            </Card>
          ))}
        </section>
      ) : signedIn ? (
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {stats.map((stat) => (
            <Card key={stat.label}>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">{stat.label}</p>
                <p className="mt-2 text-3xl font-semibold">{stat.value}</p>
              </CardContent>
            </Card>
          ))}
        </section>
      ) : (
        <SignInRequiredPanel title="Sign in to load operational data." />
      )}
    </>
  );
}
