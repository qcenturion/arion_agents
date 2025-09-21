"use client";

import { useState } from "react";
import clsx from "clsx";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { fetchAgents, fetchNetworks, fetchTools, fetchSnapshots } from "@/lib/api/config";
import type { AgentSummary, NetworkSummary, SnapshotSummary, ToolSummary } from "@/lib/api/types";

const TABS = [
  { id: "networks", label: "Networks" },
  { id: "agents", label: "Agents" },
  { id: "tools", label: "Tools" },
  { id: "snapshots", label: "Snapshots" }
] as const;

type TabId = (typeof TABS)[number]["id"];

export function ConfigWorkbench() {
  const [tab, setTab] = useState<TabId>("networks");
  const networksQuery = useQuery({ queryKey: ["networks"], queryFn: fetchNetworks, staleTime: 60_000 });
  const agentsQuery = useQuery({ queryKey: ["agents"], queryFn: fetchAgents, staleTime: 60_000 });
  const toolsQuery = useQuery({ queryKey: ["tools"], queryFn: fetchTools, staleTime: 60_000 });
  const snapshotsQuery = useQuery({ queryKey: ["snapshots"], queryFn: fetchSnapshots, staleTime: 60_000 });

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-surface/70">
      <div className="border-b border-white/5 px-6 py-4">
        <h1 className="text-2xl font-semibold text-foreground">Configuration</h1>
        <p className="mt-2 text-sm text-foreground/60">
          Manage networks, agents, tools, and published snapshots. CRUD operations are driven by the FastAPI control plane endpoints.
        </p>
        <div className="mt-6 flex gap-3">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={clsx(
                "rounded px-3 py-1 text-sm transition-colors",
                tab === item.id ? "bg-primary/20 text-primary" : "border border-white/10 text-foreground/70 hover:border-white/30"
              )}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
        {tab === "networks" ? <NetworksPanel query={networksQuery} /> : null}
        {tab === "agents" ? <AgentsPanel query={agentsQuery} /> : null}
        {tab === "tools" ? <ToolsPanel query={toolsQuery} /> : null}
        {tab === "snapshots" ? <SnapshotsPanel query={snapshotsQuery} /> : null}
      </div>
    </div>
  );
}

function NetworksPanel({ query }: { query: UseQueryResult<NetworkSummary[]> }) {
  if (query.isLoading) return <LoadingState label="networks" />;
  if (query.isError) return <ErrorState error={query.error as Error} />;
  const list = query.data ?? [];
  return (
    <table className="min-w-full text-sm">
      <thead className="text-left text-xs uppercase tracking-wide text-foreground/50">
        <tr>
          <th className="pb-2">Network</th>
          <th className="pb-2">Description</th>
          <th className="pb-2">Active snapshot</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-white/5">
        {list.map((item) => (
          <tr key={item.id}>
            <td className="py-3 font-medium">{item.name}</td>
            <td className="py-3 text-foreground/60">{item.description ?? "—"}</td>
            <td className="py-3 font-mono text-xs text-primary">{item.current_version_id ?? "unpublished"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AgentsPanel({ query }: { query: UseQueryResult<AgentSummary[]> }) {
  if (query.isLoading) return <LoadingState label="agents" />;
  if (query.isError) return <ErrorState error={query.error as Error} />;
  const list = query.data ?? [];
  return (
    <div className="space-y-4">
      {list.map((agent) => (
        <article key={agent.id} className="rounded border border-white/10 bg-background/30 p-4">
          <header className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-foreground">{agent.display_name ?? agent.key}</h3>
              <p className="text-xs font-mono text-foreground/40">{agent.key}</p>
              <p className="mt-1 text-sm text-foreground/60">{agent.description ?? "No description."}</p>
            </div>
          </header>
          <section className="mt-3">
            <h4 className="text-xs uppercase tracking-wide text-foreground/50">Tools</h4>
            {agent.equipped_tools.length ? (
              <ul className="mt-2 flex flex-wrap gap-2 text-xs">
                {agent.equipped_tools.map((toolKey) => (
                  <li key={toolKey} className="rounded border border-white/10 bg-background/40 px-2 py-1 font-mono text-foreground/80">
                    {toolKey}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-xs text-foreground/50">No tools equipped.</p>
            )}
          </section>
          <section className="mt-3">
            <h4 className="text-xs uppercase tracking-wide text-foreground/50">Routes</h4>
            {agent.allowed_routes.length ? (
              <ul className="mt-2 flex flex-wrap gap-2 text-xs">
                {agent.allowed_routes.map((routeKey) => (
                  <li key={routeKey} className="rounded border border-white/10 bg-background/40 px-2 py-1 font-mono text-foreground/80">
                    {routeKey}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-xs text-foreground/50">No downstream routes configured.</p>
            )}
          </section>
        </article>
      ))}
    </div>
  );
}

function ToolsPanel({ query }: { query: UseQueryResult<ToolSummary[]> }) {
  if (query.isLoading) return <LoadingState label="tools" />;
  if (query.isError) return <ErrorState error={query.error as Error} />;
  const list = query.data ?? [];
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {list.map((tool) => (
        <li key={tool.id} className="rounded border border-white/10 bg-background/30 p-4 text-sm">
          <h3 className="text-base font-semibold text-foreground">{tool.display_name ?? tool.key}</h3>
          <p className="text-xs font-mono text-foreground/40">{tool.key}</p>
          <p className="mt-2 text-foreground/60">{tool.description ?? "No description provided."}</p>
        </li>
      ))}
    </ul>
  );
}

function SnapshotsPanel({ query }: { query: UseQueryResult<SnapshotSummary[]> }) {
  if (query.isLoading) return <LoadingState label="snapshots" />;
  if (query.isError) return <ErrorState error={query.error as Error} />;
  const list = query.data ?? [];
  return (
    <table className="min-w-full text-sm">
      <thead className="text-left text-xs uppercase tracking-wide text-foreground/50">
        <tr>
          <th className="pb-2">Snapshot</th>
          <th className="pb-2">Graph version</th>
          <th className="pb-2">Network</th>
          <th className="pb-2">Created</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-white/5">
        {list.map((snapshot) => (
          <tr key={snapshot.snapshot_id}>
            <td className="py-3 font-mono text-xs text-foreground">{snapshot.snapshot_id}</td>
            <td className="py-3 font-mono text-xs text-primary">{snapshot.graph_version_id}</td>
            <td className="py-3 text-foreground/70">{snapshot.network_id}</td>
            <td className="py-3 text-foreground/60">{new Date(snapshot.created_at).toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function LoadingState({ label }: { label: string }) {
  return <div className="text-sm text-foreground/60">Loading {label}…</div>;
}

function ErrorState({ error }: { error: Error }) {
  return <div className="text-sm text-danger">{error.message}</div>;
}
