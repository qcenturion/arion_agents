"use client";

import { useMemo } from "react";
import clsx from "clsx";
import { usePlaybackStore } from "@/stores/usePlaybackStore";
import { useSelectionStore } from "@/stores/useSelectionStore";
import type { RunEnvelope } from "@/lib/api/types";
import {
  describeNonLogStep,
  summarizeAgentPayload,
  summarizeToolPayload,
  type TimelineStatus
} from "./stepSummaries";

export function TraceTimelinePanel() {
  const steps = usePlaybackStore((state) => state.steps);
  const cursorSeq = usePlaybackStore((state) => state.cursorSeq);
  const status = usePlaybackStore((state) => state.status);
  const setCursor = usePlaybackStore((state) => state.seekTo);
  const selectEvidence = useSelectionStore((state) => state.selectEvidence);

  const items = useMemo(
    () => steps.map((step) => buildTimelineItem(step)),
    [steps]
  );

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
          const timestamp = item.timestamp ?? Date.now();
          return (
            <li
              key={item.seq}
              className={clsx(
                "rounded-lg border border-white/5 bg-surface/80 p-4 shadow-sm transition-colors",
                active && "border-primary/60 shadow-floating"
              )}
            >
              <button
                type="button"
                onClick={() => setCursor(item.seq)}
                className="w-full text-left focus:outline-none"
              >
                <div className="flex items-start justify-between text-xs uppercase tracking-wide text-foreground/60">
                  <div className="flex items-center gap-3">
                    <span
                      className={clsx(
                        "h-2.5 w-2.5 rounded-full border shadow-sm",
                        statusClasses(item.status)
                      )}
                      aria-hidden
                    />
                    <div className="space-y-0.5">
                      <div className="font-mono text-foreground">
                        Step {item.seq}
                        {item.headerSuffix ? ` - ${item.headerSuffix}` : ""}
                      </div>
                      {item.subLabel ? (
                        <div className="text-[10px] uppercase tracking-wide text-foreground/45">
                          {item.subLabel}
                        </div>
                      ) : null}
                    </div>
                  </div>
                  <time dateTime={new Date(timestamp).toISOString()} className="text-foreground/55">
                    {new Date(timestamp).toLocaleTimeString()}
                  </time>
                </div>
                <div className="mt-3 text-sm text-foreground">
                  <div className="font-semibold">Action: {item.actionLabel}</div>
                  {item.detailLabel ? (
                    <div className="mt-1 text-xs text-foreground/70">{item.detailLabel}</div>
                  ) : null}
                  {item.secondaryDetail ? (
                    <div className="mt-1 text-xs text-foreground/50">{item.secondaryDetail}</div>
                  ) : null}
                </div>
                {item.extra ? <div className="mt-3 text-xs text-foreground/60">{item.extra}</div> : null}
              </button>
              {item.step.step.kind === "attach_evidence" && item.step.step.evidenceIds?.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
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

interface TimelineItem {
  seq: number;
  timestamp?: number;
  actionLabel: string;
  detailLabel?: string;
  secondaryDetail?: string;
  headerSuffix?: string;
  subLabel?: string;
  extra?: string;
  status: TimelineStatus;
  step: RunEnvelope;
}

function buildTimelineItem(envelope: RunEnvelope): TimelineItem {
  const { step } = envelope;
  if (step.kind !== "log_entry") {
    const summary = describeNonLogStep(step);
    return {
      seq: envelope.seq,
      timestamp: envelope.t,
      actionLabel: step.kind.replace(/_/g, " ").toUpperCase(),
      detailLabel: summary.label,
      secondaryDetail: summary.detail,
      status: "unknown",
      step: envelope
    };
  }

  if (step.entryType === "agent") {
    const summary = summarizeAgentPayload(step.payload as Record<string, unknown> | undefined);
    return {
      seq: envelope.seq,
      timestamp: envelope.t,
      actionLabel: summary.actionLabel,
      detailLabel: summary.detailLabel,
      secondaryDetail: summary.reasonLabel,
      subLabel: summary.actorLabel,
      status: summary.status,
      extra: summary.duration != null ? `Duration: ${summary.duration} ms` : undefined,
      step: envelope
    };
  }

  if (step.entryType === "tool") {
    const summary = summarizeToolPayload(step.payload as Record<string, unknown> | undefined);
    return {
      seq: envelope.seq,
      timestamp: envelope.t,
      actionLabel: "TOOL EXECUTION",
      detailLabel: summary.detailLabel,
      secondaryDetail: summary.statusLabel,
      subLabel: `Tool · ${summary.toolLabel}`,
      status: summary.status,
      extra: summary.duration != null ? `Duration: ${summary.duration} ms` : undefined,
      step: envelope
    };
  }

  return {
    seq: envelope.seq,
    timestamp: envelope.t,
    actionLabel: `LOG (${String(step.entryType ?? "entry").toUpperCase()})`,
    detailLabel: "Inspect details for full payload",
    status: "unknown",
    step: envelope
  };
}

function statusClasses(status: TimelineStatus) {
  switch (status) {
    case "success":
      return "border-emerald-400/60 bg-emerald-500/80";
    case "failure":
      return "border-red-500/70 bg-red-500/80";
    default:
      return "border-foreground/25 bg-foreground/15";
  }
}
