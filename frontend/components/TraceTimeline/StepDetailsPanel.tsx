"use client";

import { useMemo } from "react";
import { useCurrentStep } from "@/stores/usePlaybackStore";
import { summarizeAgentPayload, summarizeToolPayload, type TimelineStatus } from "./stepSummaries";

export function StepDetailsPanel() {
  const current = useCurrentStep();

  const content = useMemo(() => {
    if (!current) {
      return <p className="text-sm text-foreground/60">Select a timeline entry to inspect prompts, tool payloads, and timings.</p>;
    }
    if (current.step.kind !== "log_entry") {
      return (
        <div className="space-y-3 text-sm text-foreground/70">
          <p className="font-medium text-foreground">Unsupported step</p>
          <p>This viewer currently supports agent/tool log entries.</p>
          <pre className="whitespace-pre-wrap break-words font-mono text-xs text-foreground/60">
            {JSON.stringify(current.step, null, 2)}
          </pre>
        </div>
      );
    }
    const payload = current.step.payload as Record<string, unknown>;
    if (current.step.entryType === "agent") {
      return <AgentStepDetail payload={payload} />;
    }
    if (current.step.entryType === "tool") {
      return <ToolStepDetail payload={payload} />;
    }
    return (
      <div className="space-y-3 text-sm text-foreground/70">
        <p className="font-medium text-foreground">Log entry</p>
        <pre className="whitespace-pre-wrap break-words font-mono text-xs text-foreground/60">
          {JSON.stringify(payload, null, 2)}
        </pre>
      </div>
    );
  }, [current]);

  const timestampLabel = current ? new Date(current.t).toLocaleString() : null;

  return (
    <aside className="hidden w-[420px] flex-col border-l border-white/5 bg-surface/80 lg:flex">
      <div className="border-b border-white/5 px-4 py-3">
        <div className="text-xs uppercase tracking-wide text-foreground/50">Step Detail</div>
        {current ? (
          <div className="mt-1 flex items-center justify-between text-xs text-foreground/60">
            <span className="font-mono text-foreground">#{current.seq}</span>
            <span>{timestampLabel}</span>
          </div>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4 text-sm text-foreground/80">{content}</div>
    </aside>
  );
}

function AgentStepDetail({ payload }: { payload: Record<string, unknown> }) {
  const prompt = typeof payload.prompt === "string" ? payload.prompt : null;
  const raw = typeof payload.raw_response === "string" ? payload.raw_response : null;
  const decision = payload.decision_full ?? payload.decision;
  const timing = payload.timing as Record<string, unknown> | undefined;
  const summary = summarizeAgentPayload(payload);
  const statusTone = toneForStatus(summary.status);
  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <p className="text-xs uppercase tracking-wide text-foreground/50">Agent</p>
        <p className="font-mono text-sm text-foreground">{String(payload.agent_key ?? "agent")}</p>
        <p className="text-xs text-foreground/60">Action · {summary.actionLabel}</p>
        {summary.detailLabel ? (
          <p className="text-[11px] text-foreground/50">{summary.detailLabel}</p>
        ) : null}
        <p className={`text-[11px] ${statusTone}`}>Status · {statusText(summary.status)}</p>
        {summary.reasonLabel ? (
          <p className="text-xs text-foreground/55">Reasoning · {summary.reasonLabel}</p>
        ) : null}
      </header>
      {prompt ? (
        <section className="space-y-2">
          <h3 className="text-xs uppercase tracking-wide text-foreground/50">Prompt</h3>
          <PreformattedBlock value={prompt} />
        </section>
      ) : null}
      {raw ? (
        <section className="space-y-2">
          <h3 className="text-xs uppercase tracking-wide text-foreground/50">LLM response</h3>
          <PreformattedBlock value={raw} />
        </section>
      ) : null}
      {decision ? (
        <section className="space-y-2">
          <h3 className="text-xs uppercase tracking-wide text-foreground/50">Decision</h3>
          <PreformattedJson value={decision} />
        </section>
      ) : null}
      {timing ? (
        <section className="space-y-2">
          <h3 className="text-xs uppercase tracking-wide text-foreground/50">Timing (ms)</h3>
          <KeyValueTable data={timing} />
        </section>
      ) : null}
    </div>
  );
}

function ToolStepDetail({ payload }: { payload: Record<string, unknown> }) {
  const timing = payload.timing as Record<string, unknown> | undefined;
  const requestPayload = payload.request_payload ?? payload.request_preview;
  const responsePayload = payload.response_payload ?? payload.response_preview;
  const summary = summarizeToolPayload(payload);
  const statusTone = toneForStatus(summary.status);
  const statusValue = String(payload.status ?? "unknown");
  const totalDuration = typeof payload.total_duration_ms === "number" ? payload.total_duration_ms : null;
  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <p className="text-xs uppercase tracking-wide text-foreground/50">Tool</p>
        <p className="font-mono text-sm text-foreground">{String(payload.tool_key ?? "tool")}</p>
        {summary.actorLabel ? (
          <p className="text-[11px] text-foreground/50">{summary.actorLabel}</p>
        ) : null}
        <p className="text-xs text-foreground/60">Action · TOOL</p>
        <p className={`text-[11px] ${statusTone}`}>Status · {statusValue}</p>
        {summary.duration != null ? (
          <p className="text-[11px] text-foreground/50">Duration · {summary.duration} ms</p>
        ) : null}
        {totalDuration != null ? (
          <p className="text-[11px] text-foreground/45">Total duration · {totalDuration} ms</p>
        ) : null}
      </header>
      {requestPayload ? (
        <section className="space-y-2">
          <h3 className="text-xs uppercase tracking-wide text-foreground/50">Request</h3>
          <PreformattedJson value={requestPayload} />
        </section>
      ) : null}
      {responsePayload ? (
        <section className="space-y-2">
          <h3 className="text-xs uppercase tracking-wide text-foreground/50">Response</h3>
          <PreformattedJson value={responsePayload} />
        </section>
      ) : null}
      {timing ? (
        <section className="space-y-2">
          <h3 className="text-xs uppercase tracking-wide text-foreground/50">Timing (ms)</h3>
          <KeyValueTable data={timing} />
        </section>
      ) : null}
    </div>
  );
}

function PreformattedBlock({ value }: { value: string }) {
  return (
    <pre className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded border border-white/10 bg-background/40 p-3 font-mono text-xs text-foreground/80">
      {value}
    </pre>
  );
}

function PreformattedJson({ value }: { value: unknown }) {
  return (
    <PreformattedBlock value={formatJson(value)} />
  );
}

function KeyValueTable({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data ?? {});
  if (!entries.length) return null;
  return (
    <dl className="space-y-2 text-xs">
      {entries.map(([key, value]) => (
        <div key={key} className="flex gap-3">
          <dt className="w-28 text-foreground/50">{key}</dt>
          <dd className="flex-1 break-words font-mono text-foreground/80">{String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function formatJson(value: unknown): string {
  try {
    if (typeof value === "string") {
      return value;
    }
    return JSON.stringify(value, null, 2);
  } catch (error) {
    return String(value);
  }
}

function statusText(status: TimelineStatus): string {
  switch (status) {
    case "success":
      return "Success";
    case "failure":
      return "Failure";
    default:
      return "Unknown";
  }
}

function toneForStatus(status: TimelineStatus): string {
  switch (status) {
    case "success":
      return "text-emerald-400";
    case "failure":
      return "text-danger/80";
    default:
      return "text-foreground/45";
  }
}
