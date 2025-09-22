"use client";

import { useEffect, useMemo } from "react";
import { subscribeToRunSteps } from "@/lib/api/runs";
import type { RunEnvelope } from "@/lib/api/types";
import { summariseRunLatency, formatDuration } from "@/lib/latency/summary";
import { usePlaybackStore } from "@/stores/usePlaybackStore";
import { useRunViewStore } from "@/stores/useRunViewStore";
import { TraceTimelinePanel } from "./TraceTimelinePanel";
import { EvidencePanel } from "@/components/EvidencePanel/EvidencePanel";
import { PlaybackToolbar } from "@/components/RunControls/PlaybackToolbar";
import { StepDetailsPanel } from "@/components/TraceTimeline/StepDetailsPanel";
import { RunFlowGraph } from "@/components/RunFlow/RunFlowGraph";

interface RunPlaybackProps {
  traceId: string;
  initialSteps: RunEnvelope[];
  graphVersionId?: string | null;
}

export function RunPlayback({ traceId, initialSteps }: RunPlaybackProps) {
  const setInitialSteps = usePlaybackStore((state) => state.setInitialSteps);
  const appendStep = usePlaybackStore((state) => state.appendStep);
  const reset = usePlaybackStore((state) => state.reset);
  const steps = usePlaybackStore((state) => state.steps);
  const view = useRunViewStore((state) => state.view);

  useEffect(() => {
    setInitialSteps(initialSteps);
    return () => {
      reset();
    };
  }, [initialSteps, setInitialSteps, reset]);

  useEffect(() => {
    if (!traceId) return undefined;
    const lastSeq = initialSteps.length ? initialSteps[initialSteps.length - 1].seq : undefined;
    const source = subscribeToRunSteps({
      traceId,
      fromSeq: lastSeq,
      onEvent: (step) => {
        appendStep(step);
      }
    });
    return () => source.close();
  }, [traceId, initialSteps, appendStep]);

  const latency = useMemo(() => summariseRunLatency(steps), [steps]);

  const content = view === "timeline" ? (
    <div className="flex w-[360px] flex-col border-r border-white/5 bg-surface/70">
      <PlaybackToolbar traceId={traceId} />
      <div className="flex min-h-0 flex-1 flex-col">
        <TraceTimelinePanel />
      </div>
      {latency ? (
        <div className="border-t border-white/5 px-4 py-3 text-xs text-foreground/50">
          Total latency · {formatDuration(latency.totalMs)}
        </div>
      ) : null}
    </div>
  ) : (
    <div className="flex min-w-0 flex-1 flex-col border-r border-white/5 bg-surface/70">
      <PlaybackToolbar traceId={traceId} />
      <RunFlowGraph steps={steps} />
    </div>
  );

  return (
    <div className="flex h-full min-h-0 flex-1 flex-row">
      {content}
      <StepDetailsPanel />
      <EvidencePanel />
    </div>
  );
}
