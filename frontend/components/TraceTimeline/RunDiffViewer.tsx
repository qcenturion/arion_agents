"use client";

import { useMemo } from "react";
import clsx from "clsx";
import type { RunEnvelope } from "@/lib/api/types";

interface RunDiffViewerProps {
  primaryTraceId: string;
  secondaryTraceId: string;
  primarySteps: RunEnvelope[];
  secondarySteps: RunEnvelope[];
  graphVersionId: string;
}

export function RunDiffViewer({ primaryTraceId, secondaryTraceId, primarySteps, secondarySteps }: RunDiffViewerProps) {
  const diffRows = useMemo(() => computeDiffRows(primarySteps, secondarySteps), [primarySteps, secondarySteps]);

  return (
    <div className="flex h-full min-h-0 flex-1 overflow-hidden">
      <div className="flex w-1/2 flex-col border-r border-white/5">
        <DiffColumnHeader label="Primary" traceId={primaryTraceId} />
        <DiffColumnList rows={diffRows} side="primary" />
      </div>
      <div className="flex w-1/2 flex-col">
        <DiffColumnHeader label="Secondary" traceId={secondaryTraceId} />
        <DiffColumnList rows={diffRows} side="secondary" />
      </div>
    </div>
  );
}

interface DiffRow {
  seq: number;
  primary?: RunEnvelope;
  secondary?: RunEnvelope;
  status: "match" | "mismatch" | "primary-only" | "secondary-only";
}

function computeDiffRows(primary: RunEnvelope[], secondary: RunEnvelope[]): DiffRow[] {
  const bySeq = new Map<number, DiffRow>();
  primary.forEach((step) => {
    const existing = bySeq.get(step.seq) ?? { seq: step.seq, status: "primary-only" as DiffRow["status"] };
    existing.primary = step;
    bySeq.set(step.seq, existing);
  });

  secondary.forEach((step) => {
    const existing = bySeq.get(step.seq) ?? { seq: step.seq, status: "secondary-only" as DiffRow["status"] };
    existing.secondary = step;
    bySeq.set(step.seq, existing);
  });

  return Array.from(bySeq.values())
    .map((row) => {
      if (row.primary && row.secondary) {
        row.status = JSON.stringify(row.primary.step) === JSON.stringify(row.secondary.step) ? "match" : "mismatch";
      } else if (row.primary) {
        row.status = "primary-only";
      } else if (row.secondary) {
        row.status = "secondary-only";
      }
      return row;
    })
    .sort((a, b) => a.seq - b.seq);
}

function DiffColumnHeader({ label, traceId }: { label: string; traceId: string }) {
  return (
    <div className="border-b border-white/5 bg-surface/70 px-4 py-3 text-xs uppercase tracking-wide text-foreground/50">
      {label} · <span className="font-mono text-foreground/70">{traceId}</span>
    </div>
  );
}

function DiffColumnList({ rows, side }: { rows: DiffRow[]; side: "primary" | "secondary" }) {
  return (
    <ol className="min-h-0 flex-1 space-y-2 overflow-y-auto bg-surface/50 px-4 py-4">
      {rows.map((row) => {
        const step = row[side];
        const active = row.status === "mismatch" || row.status === `${side}-only`;
        return (
          <li
            key={`${row.seq}-${side}`}
            className={clsx(
              "rounded border border-white/5 bg-background/30 p-3 text-sm transition-colors",
              active ? "border-warning/60" : "border-white/5",
              row.status === "match" ? "text-foreground/70" : "text-foreground"
            )}
          >
            <div className="flex items-center justify-between text-xs uppercase tracking-wide text-foreground/40">
              <span className="font-mono">#{row.seq}</span>
              <span>{statusLabel(row.status)}</span>
            </div>
            {step ? (
              <div className="mt-2">
                <div className="font-semibold">{describeStep(step)}</div>
                <pre className="mt-2 whitespace-pre-wrap break-words font-mono text-xs text-foreground/60">
                  {JSON.stringify(step.step, null, 2)}
                </pre>
              </div>
            ) : (
              <div className="mt-2 text-xs text-foreground/60">–</div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function describeStep(envelope: RunEnvelope) {
  switch (envelope.step.kind) {
    case "visit_node":
      return `Visit ${envelope.step.nodeId}`;
    case "traverse_edge":
      return `Traverse ${envelope.step.edgeKey}`;
    case "attach_evidence":
      return `Attach evidence (${envelope.step.evidenceIds.length})`;
    case "vector_lookup":
      return `Vector lookup (${envelope.step.hits.length} hits)`;
    case "cypher":
      return `Cypher query`; // details below
    default:
      return envelope.step.kind;
  }
}

function statusLabel(status: DiffRow["status"]) {
  switch (status) {
    case "match":
      return "match";
    case "mismatch":
      return "mismatch";
    case "primary-only":
      return "only primary";
    case "secondary-only":
      return "only secondary";
    default:
      return status;
  }
}
