"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { fetchGraphSnapshots } from "@/lib/api/graphs";

export function GraphList() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["graph-snapshots"],
    queryFn: fetchGraphSnapshots,
    staleTime: 120_000
  });

  if (isLoading) {
    return <div className="p-6 text-sm text-foreground/60">Gathering snapshots…</div>;
  }

  if (isError) {
    return (
      <div className="p-6 text-sm text-warning">
        Failed to load graph snapshots: {(error as Error).message}
      </div>
    );
  }

  if (!data?.length) {
    return <div className="p-6 text-sm text-foreground/60">No snapshots have been published yet.</div>;
  }

  return (
    <ul className="divide-y divide-white/5">
      {data.map((snapshot) => (
        <li key={snapshot.snapshot_id} className="flex items-center justify-between px-6 py-4 hover:bg-surface/70">
          <div>
            <p className="text-sm font-medium text-foreground">
              Graph {snapshot.graph_version_id}
            </p>
            <p className="text-xs text-foreground/60">Network {snapshot.network_id}</p>
          </div>
          <div className="flex items-center gap-3 text-sm text-foreground/60">
            <time dateTime={snapshot.created_at}>
              {new Date(snapshot.created_at).toLocaleString()}
            </time>
            <Link
              href={`/graphs/${snapshot.graph_version_id}`}
              className="rounded border border-primary/40 px-3 py-1 text-xs text-primary hover:bg-primary/10"
            >
              Inspect
            </Link>
          </div>
        </li>
      ))}
    </ul>
  );
}
