import { Suspense } from "react";
import { RunConsole } from "@/components/RunControls/RunConsole";
import { StepDetailsPanel } from "@/components/TraceTimeline/StepDetailsPanel";
import { EvidencePanel } from "@/components/EvidencePanel/EvidencePanel";
import { RunWorkspace } from "@/components/RunControls/RunWorkspace";

export default function HomePage() {
  return (
    <div className="flex h-full min-h-0 flex-1 overflow-hidden">
      <div className="flex w-full max-w-sm flex-col border-r border-white/5 bg-surface/60 backdrop-blur">
        <Suspense fallback={<div className="p-6 text-sm text-foreground/60">Loading run controls…</div>}>
          <RunConsole />
        </Suspense>
      </div>
      <div className="flex min-w-0 flex-1 flex-row">
        <div className="flex min-w-0 flex-1 flex-row">
          <div className="flex min-w-0 flex-1 flex-col">
            <Suspense fallback={<div className="p-6 text-sm text-foreground/60">Loading timeline…</div>}>
              <RunWorkspace />
            </Suspense>
          </div>
          <Suspense fallback={null}>
            <StepDetailsPanel />
          </Suspense>
        </div>
        <Suspense fallback={null}>
          <EvidencePanel />
        </Suspense>
      </div>
    </div>
  );
}
