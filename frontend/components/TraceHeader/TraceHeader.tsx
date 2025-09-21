"use client";

import { useState } from "react";
import clsx from "clsx";

interface TraceHeaderProps {
  traceId?: string;
  graphVersionId?: string;
  otherTraceId?: string;
  latencyMs?: number;
}

export function TraceHeader({ traceId, graphVersionId, otherTraceId, latencyMs }: TraceHeaderProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!traceId) return;
    try {
      await navigator.clipboard.writeText(traceId);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error("Failed to copy trace id", error);
    }
  };

  return (
    <div className="flex items-center justify-between border-b border-white/5 bg-surface/80 px-6 py-3 text-xs uppercase tracking-wide text-foreground/60">
      <div className="flex items-center gap-4">
        {traceId ? (
          <div className="flex items-center gap-2">
            <span className="text-foreground/70">Trace</span>
            <span className="font-mono text-foreground">{truncate(traceId)}</span>
            <button
              type="button"
              className={clsx(
                "rounded border px-2 py-1 font-semibold transition-colors",
                copied ? "border-success text-success" : "border-white/10 text-foreground/80 hover:border-white/30"
              )}
              onClick={handleCopy}
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        ) : null}
        {graphVersionId ? (
          <div className="flex items-center gap-2">
            <span className="text-foreground/70">Graph</span>
            <span className="font-mono text-foreground">{graphVersionId}</span>
          </div>
        ) : null}
        {otherTraceId ? (
          <div className="flex items-center gap-2 text-secondary">
            <span className="text-foreground/70">vs</span>
            <span className="font-mono">{truncate(otherTraceId)}</span>
          </div>
        ) : null}
      </div>
      {typeof latencyMs === "number" ? (
        <div className="text-foreground/60">{formatLatency(latencyMs)}</div>
      ) : null}
    </div>
  );
}

function truncate(value: string) {
  if (value.length <= 12) return value;
  return `${value.slice(0, 6)}…${value.slice(-4)}`;
}

function formatLatency(ms: number) {
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}m ${remainder.toFixed(0)}s`;
}
