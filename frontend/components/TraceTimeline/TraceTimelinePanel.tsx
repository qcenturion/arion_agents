"use client";

import { useMemo } from "react";
import clsx from "clsx";
import { usePlaybackStore } from "@/stores/usePlaybackStore";
import { useSelectionStore } from "@/stores/useSelectionStore";
import type { RunEnvelope } from "@/lib/api/types";

export function TraceTimelinePanel() {
  const steps = usePlaybackStore((state) => state.steps);
  const cursorSeq = usePlaybackStore((state) => state.cursorSeq);
  const status = usePlaybackStore((state) => state.status);
  const setCursor = usePlaybackStore((state) => state.seekTo);
  const selectEvidence = useSelectionStore((state) => state.selectEvidence);

  const items = useMemo(() => steps.map((step) => ({
      seq: step.seq,
      label: describeStep(step),
      timestamp: step.t,
      step
    })), [steps]);

  if (!items.length) {
    return (
      <div className="flex flex-1 items-center justify-center p-10 text-sm text-foreground/60">
        Trigger a run to inspect its execution timeline.
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-surface/60 px-6 py-6">
      <ol className="space-y-4" aria-live={status === "live" ? "polite" : "off"}>
        {items.map((item) => {
          const active = item.seq === cursorSeq;
          return (
            <li
              key={item.seq}
              className={clsx(
                "rounded-lg border border-white/5 bg-surface/80 p-4 shadow-sm transition-colors",
                active && "border-primary/60 shadow-floating"
              )}
            >
              <div className="flex items-center justify-between text-xs uppercase tracking-wide text-foreground/50">
                <span className="font-mono">#{item.seq}</span>
                <time dateTime={new Date(item.timestamp).toISOString()}>
                  {new Date(item.timestamp).toLocaleTimeString()}
                </time>
              </div>
              <button
                type="button"
                onClick={() => setCursor(item.seq)}
                className="mt-2 text-left text-sm font-medium text-foreground hover:text-primary"
              >
                {item.label}
              </button>
              {item.step.step.kind === "attach_evidence" && item.step.step.evidenceIds?.length ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {item.step.step.evidenceIds.map((id) => (
                    <button
                      type="button"
                      key={id}
                      className="rounded bg-primary/10 px-2 py-1 text-xs font-mono text-primary"
                      onClick={() => selectEvidence(id)}
                    >
                      {id}
                    </button>
                  ))}
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function describeStep(envelope: RunEnvelope) {
  const { step } = envelope;
  switch (step.kind) {
    case "visit_node":
      return `Visited ${step.nodeId}`;
    case "traverse_edge":
      return `Traversed ${step.edgeKey}`;
    case "attach_evidence":
      return `Attached evidence (${step.evidenceIds.length})`;
    case "vector_lookup":
      return `Vector lookup (${step.hits.length} hits)`;
    case "cypher":
      return `Cypher query (${step.duration_ms} ms)`;
    case "log_entry": {
      const entryType = step.entryType;
      const payload = step.payload ?? {};
      if (entryType === "agent") {
        const agent = String((payload as Record<string, unknown>).agent_key ?? "agent");
        const decision = (payload as Record<string, unknown>).decision as Record<string, unknown> | undefined;
        const action = decision?.action ?? decision?.type;
        return action ? `Agent ${agent} → ${String(action)}` : `Agent ${agent} step`;
      }
      if (entryType === "tool") {
        const tool = String((payload as Record<string, unknown>).tool_key ?? "tool");
        const status = String((payload as Record<string, unknown>).status ?? "");
        return status ? `Tool ${tool} (${status})` : `Tool ${tool} invocation`;
      }
      return `Log entry (${entryType})`;
    }
    default:
      return step.kind;
  }
}
