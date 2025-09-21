import { Suspense } from "react";
import { notFound } from "next/navigation";
import { GraphViewer } from "@/components/GraphCanvas/GraphViewer";
import { fetchGraph } from "@/lib/api/graphs";
import { TraceHeader } from "@/components/TraceHeader/TraceHeader";

interface GraphPageProps {
  params: { graphVersionId: string };
}

export default async function GraphVersionPage({ params }: GraphPageProps) {
  const graph = await fetchGraph(params.graphVersionId);

  if (!graph) {
    notFound();
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <TraceHeader graphVersionId={params.graphVersionId} />
      <Suspense fallback={<div className="p-6 text-sm text-foreground/60">Loading graph…</div>}>
        <GraphViewer graphVersionId={params.graphVersionId} staticGraph={graph} />
      </Suspense>
    </div>
  );
}
