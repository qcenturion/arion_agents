import Link from "next/link";
import { Suspense } from "react";
import { GraphList } from "@/components/GraphCanvas/GraphList";

export default function GraphsIndexPage() {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-white/5 bg-surface/80 p-6 backdrop-blur">
        <h1 className="text-2xl font-semibold">Graphs</h1>
        <p className="mt-2 max-w-2xl text-sm text-foreground/70">
          Browse published Network graphs. Layout coordinates are persisted by the backend and rendered as-is for deterministic auditing.
        </p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <Suspense fallback={<div className="p-6 text-sm text-foreground/60">Loading graphs…</div>}>
          <GraphList />
        </Suspense>
      </div>
      <div className="border-t border-white/5 bg-surface/60 p-4 text-sm text-foreground/60">
        Need a new snapshot?&nbsp;
        <Link href="/config" className="text-primary hover:underline">
          Publish via Config → Snapshots
        </Link>
      </div>
    </div>
  );
}
