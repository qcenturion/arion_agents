import { Suspense } from "react";
import { notFound } from "next/navigation";
import { RunPlayback } from "@/components/TraceTimeline/RunPlayback";
import { GraphViewer } from "@/components/GraphCanvas/GraphViewer";
import { TraceHeader } from "@/components/TraceHeader/TraceHeader";
import { fetchRunSnapshot } from "@/lib/api/runs";

interface RunPageProps {
  params: { traceId: string };
  searchParams: { [key: string]: string | string[] | undefined };
}

export default async function RunPage({ params }: RunPageProps) {
  const run = await fetchRunSnapshot(params.traceId);

  if (!run) {
    notFound();
  }

  const graphVersionId = run.graphVersionId ?? run.metadata?.graph_version_key ?? null;

  return (
    <div className="flex h-full min-h-0 flex-1 flex-row overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col">
        <TraceHeader traceId={params.traceId} graphVersionId={graphVersionId ?? undefined} />
        <div className="flex min-h-0 flex-1 flex-row divide-x divide-white/5">
          <div className="flex min-w-0 flex-1 flex-col">
            <Suspense fallback={<div className="p-6 text-sm text-foreground/60">Loading playback…</div>}>
              <RunPlayback traceId={params.traceId} initialSteps={run.steps} graphVersionId={graphVersionId ?? undefined} />
            </Suspense>
          </div>
          {graphVersionId ? (
            <div className="hidden w-[420px] flex-col lg:flex">
              <Suspense fallback={<div className="p-6 text-sm text-foreground/60">Loading graph…</div>}>
                <GraphViewer graphVersionId={graphVersionId} focusTraceId={params.traceId} />
              </Suspense>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
