"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { fetchEvidence } from "@/lib/api/evidence";
import { useSelectionStore } from "@/stores/useSelectionStore";

export function EvidencePanel() {
  const selectedEvidenceId = useSelectionStore((state) => state.selectedEvidenceId);
  const pin = useSelectionStore((state) => state.pinEvidencePanel);
  const togglePin = useSelectionStore((state) => state.togglePinEvidence);
  const clearEvidence = useSelectionStore((state) => state.selectEvidence);

  const { data, isFetching, isError, error } = useQuery({
    queryKey: ["evidence", selectedEvidenceId],
    queryFn: () => fetchEvidence(selectedEvidenceId as string),
    enabled: Boolean(selectedEvidenceId),
    staleTime: 5 * 60 * 1000
  });

  const contentState = useMemo(() => {
    if (!selectedEvidenceId) {
      return "empty" as const;
    }
    if (isFetching) {
      return "loading" as const;
    }
    if (isError) {
      return "error" as const;
    }
    return "ready" as const;
  }, [selectedEvidenceId, isFetching, isError]);

  if (!pin && !selectedEvidenceId) {
    return null;
  }

  return (
    <aside className="flex h-full w-[360px] flex-col border-l border-white/5 bg-surface/80">
      <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
        <div className="text-xs uppercase tracking-wide text-foreground/50">Evidence</div>
        <div className="flex items-center gap-2 text-xs">
          <button
            type="button"
            className={clsx(
              "rounded border px-2 py-1 transition-colors",
              pin ? "border-success/50 text-success" : "border-white/10 text-foreground/60 hover:text-foreground"
            )}
            onClick={togglePin}
          >
            {pin ? "Pinned" : "Pin"}
          </button>
          {selectedEvidenceId ? (
            <button
              type="button"
              className="rounded border border-white/10 px-2 py-1 text-foreground/60 hover:text-warning"
              onClick={() => clearEvidence(null)}
            >
              Clear
            </button>
          ) : null}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4 text-sm text-foreground/80">
        {contentState === "empty" ? (
          <p className="text-foreground/60">Select a step with evidence to preview its payload.</p>
        ) : null}
        {contentState === "loading" ? (
          <div className="space-y-3">
            <SkeletonLine width="70%" />
            <SkeletonLine width="100%" />
            <SkeletonLine width="85%" />
            <SkeletonLine width="92%" />
          </div>
        ) : null}
        {contentState === "error" ? (
          <p className="text-danger">Failed to load evidence: {(error as Error).message}</p>
        ) : null}
        {contentState === "ready" && data ? (
          <article className="space-y-4">
            <header>
              <p className="font-mono text-xs text-primary">{selectedEvidenceId}</p>
              {data.title ? <h3 className="mt-1 text-lg font-semibold text-foreground">{data.title}</h3> : null}
            </header>
            <section className="rounded border border-white/10 bg-background/40 p-3">
              <pre className="whitespace-pre-wrap font-sans text-sm leading-6 text-foreground/90">
                {data.text}
              </pre>
            </section>
            {data.metadata ? (
              <section>
                <h4 className="text-xs uppercase tracking-wide text-foreground/50">Metadata</h4>
                <MetadataTable metadata={data.metadata} />
              </section>
            ) : null}
          </article>
        ) : null}
      </div>
    </aside>
  );
}

function SkeletonLine({ width }: { width: string }) {
  return <div className="h-3 rounded-full bg-foreground/10" style={{ width }} />;
}

function MetadataTable({ metadata }: { metadata: Record<string, unknown> }) {
  const entries = Object.entries(metadata ?? {});
  if (!entries.length) return null;
  return (
    <dl className="mt-2 space-y-2 text-xs">
      {entries.map(([key, value]) => (
        <div key={key} className="flex gap-3">
          <dt className="w-24 text-foreground/50">{key}</dt>
          <dd className="flex-1 break-words font-mono text-foreground/80">
            {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
