"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { TraceTimelinePanel } from "@/components/TraceTimeline/TraceTimelinePanel";
import { useRunViewStore } from "@/stores/useRunViewStore";
import { usePlaybackStore } from "@/stores/usePlaybackStore";

const RunFlowGraph = dynamic(() => import("@/components/RunFlow/RunFlowGraph"), {
  ssr: false,
  loading: () => (
    <div className="flex min-h-[280px] flex-1 items-center justify-center text-sm text-foreground/60">
      Loading graph…
    </div>
  )
});

export function RunWorkspace() {
  const view = useRunViewStore((state) => state.view);
  const steps = usePlaybackStore((state) => state.steps);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!expanded) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [expanded]);

  const closeExpanded = () => setExpanded(false);
  const openExpanded = () => setExpanded(true);

  if (view === "graph") {
    return (
      <>
        <RunFlowGraph steps={steps} onExpand={openExpanded} orientation="vertical" />
        {expanded ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/90 backdrop-blur">
            <div className="flex h-[90vh] w-[90vw] max-w-5xl flex-col overflow-hidden rounded-xl border border-white/10 bg-surface/95 shadow-floating">
              <header className="flex items-center justify-between border-b border-white/10 px-4 py-3">
                <div className="text-sm font-semibold text-foreground">Execution Flow Graph</div>
                <button
                  type="button"
                  className="rounded border border-white/20 px-3 py-1 text-xs uppercase tracking-wide text-foreground/70 hover:border-white/40"
                  onClick={closeExpanded}
                >
                  Close
                </button>
              </header>
              <div className="flex min-h-0 flex-1">
                <RunFlowGraph steps={steps} orientation="horizontal" />
              </div>
            </div>
          </div>
        ) : null}
      </>
    );
  }

  return <TraceTimelinePanel />;
}
