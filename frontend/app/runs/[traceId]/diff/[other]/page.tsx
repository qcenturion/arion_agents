import { Suspense } from "react";
import { notFound } from "next/navigation";
import { TraceHeader } from "@/components/TraceHeader/TraceHeader";
import { RunDiffViewer } from "@/components/TraceTimeline/RunDiffViewer";
import { DiffLegend } from "@/components/DiffLegend/DiffLegend";
import { fetchRunSnapshot } from "@/lib/api/runs";

interface RunDiffPageProps {
  params: { traceId: string; other: string };
}

export default async function RunDiffPage({ params }: RunDiffPageProps) {
  const [primary, secondary] = await Promise.all([
    fetchRunSnapshot(params.traceId),
    fetchRunSnapshot(params.other)
  ]);

  if (!primary || !secondary) {
    notFound();
  }

  const primaryGraphVersionId = primary.graphVersionId ?? primary.metadata?.graph_version_key ?? undefined;
  const secondaryGraphVersionId = secondary.graphVersionId ?? secondary.metadata?.graph_version_key ?? undefined;

  if (primaryGraphVersionId !== secondaryGraphVersionId) {
    console.warn("Run diff requested for mismatched graph versions", {
      primary: primaryGraphVersionId,
      secondary: secondaryGraphVersionId
    });
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
      <TraceHeader traceId={params.traceId} graphVersionId={primaryGraphVersionId} otherTraceId={params.other} />
      <Suspense fallback={<div className="p-6 text-sm text-foreground/60">Loading run diff…</div>}>
        <RunDiffViewer
          primaryTraceId={params.traceId}
          secondaryTraceId={params.other}
          primarySteps={primary.steps}
          secondarySteps={secondary.steps}
        />
      </Suspense>
      <DiffLegend />
    </div>
  );
}
