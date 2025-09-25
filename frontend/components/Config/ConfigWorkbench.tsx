"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";

import { AgentCard, ErrorState, LoadingState, ToolCard, extractApiErrorMessage, parseJsonObject, prettyJson } from "@/components/Config/shared";
import {
  fetchAgents,
  fetchNetworks,
  fetchTools,
  fetchSnapshots,
  type PublishNetworkPayload,
  compileAndPublishNetwork,
  updateNetwork,
  type NetworkUpdatePayload
} from "@/lib/api/config";
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
    <div className="space-y-3">
      {list.map((item) => (
        <NetworkRow key={item.id} network={item} />
      ))}
    </div>
  );
}

function NetworkRow({ network }: { network: NetworkSummary }) {
  const queryClient = useQueryClient();
  const [toast, setToast] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [description, setDescription] = useState(network.description ?? "");
  const [status, setStatus] = useState(network.status ?? "draft");
  const [additionalDataText, setAdditionalDataText] = useState(prettyJson(network.additional_data ?? {}));

  useEffect(() => {
    setDescription(network.description ?? "");
    setStatus(network.status ?? "draft");
    setAdditionalDataText(prettyJson(network.additional_data ?? {}));
    setIsEditing(false);
  }, [network.description, network.status, network.additional_data]);

  const mutation = useMutation({
    mutationFn: (payload: PublishNetworkPayload) => compileAndPublishNetwork(network.id, payload),
    onSuccess: () => {
      setErrorMessage(null);
      setToast("Published successfully");
      queryClient.invalidateQueries({ queryKey: ["networks"] });
      queryClient.invalidateQueries({ queryKey: ["snapshots"] });
    },
    onError: (err) => {
      setToast(null);
      setErrorMessage(extractApiErrorMessage(err));
    }
  });

  const updateMutation = useMutation({
    mutationFn: (payload: NetworkUpdatePayload) => updateNetwork(network.id, payload),
    onSuccess: (data) => {
      setErrorMessage(null);
      setDescription(data.description ?? "");
      setStatus(data.status ?? "draft");
      setAdditionalDataText(prettyJson(data.additional_data ?? {}));
      queryClient.invalidateQueries({ queryKey: ["networks"] });
      setIsEditing(false);
      setToast("Network updated");
    },
    onError: (err) => {
      setToast(null);
      setErrorMessage(extractApiErrorMessage(err));
    }
  });

  const resetEditState = () => {
    setDescription(network.description ?? "");
    setStatus(network.status ?? "draft");
    setAdditionalDataText(prettyJson(network.additional_data ?? {}));
    setIsEditing(false);
  };

  const handlePublish = () => {
    setErrorMessage(null);
    setToast(null);
    mutation.mutate({ notes: "manual publish", published_by: "frontend" });
  };

  const handleSave = () => {
    setErrorMessage(null);
    const parsed = parseJsonObject(additionalDataText, "Additional data");
    if (!parsed.ok) {
      setErrorMessage(parsed.message);
      return;
    }
    const payload: NetworkUpdatePayload = {
      description,
      status,
      additional_data: parsed.value
    };
    updateMutation.mutate(payload);
  };

  return (
    <div className="rounded border border-white/10 bg-background/30 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-foreground">{network.name}</h3>
          <p className="text-sm text-foreground/60">{description.trim() ? description : "No description"}</p>
          <p className="mt-1 text-xs text-foreground/50">Status: {status}</p>
          <p className="mt-1 text-xs text-foreground/50">Active snapshot: {network.current_version_id ?? "unpublished"}</p>
        </div>
        <button
          type="button"
          className="rounded bg-primary/80 px-3 py-1 text-sm text-background hover:bg-primary disabled:opacity-60"
          onClick={handlePublish}
          disabled={mutation.isPending}
        >
          {mutation.isPending ? "Publishing…" : "Publish network"}
        </button>
      </div>
      <div className="mt-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-foreground">RESPOND payload config</h4>
          <div className="flex gap-2">
            {isEditing ? (
              <>
                <button
                  type="button"
                  className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30"
                  onClick={resetEditState}
                  disabled={updateMutation.isPending}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="rounded bg-primary/80 px-3 py-1 text-xs text-background hover:bg-primary disabled:opacity-60"
                  onClick={handleSave}
                  disabled={updateMutation.isPending}
                >
                  {updateMutation.isPending ? "Saving…" : "Save changes"}
                </button>
              </>
            ) : (
              <button
                type="button"
                className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30"
                onClick={() => {
                  setIsEditing(true);
                  setToast(null);
                  setErrorMessage(null);
                }}
              >
                Edit
              </button>
            )}
          </div>
        </div>
        {isEditing ? (
          <div className="space-y-3">
            <label className="block text-xs font-medium text-foreground/70">
              Description
              <textarea
                className="mt-1 w-full rounded border border-white/10 bg-background/20 p-2 text-sm text-foreground"
                rows={2}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
            <label className="block text-xs font-medium text-foreground/70">
              Status
              <select
                className="mt-1 w-full rounded border border-white/10 bg-background/20 p-2 text-sm text-foreground"
                value={status}
                onChange={(event) => setStatus(event.target.value)}
              >
                <option value="draft">draft</option>
                <option value="published">published</option>
                <option value="archived">archived</option>
              </select>
            </label>
            <label className="block text-xs font-medium text-foreground/70">
              Additional data (JSON)
              <textarea
                className="mt-1 w-full rounded border border-white/10 bg-background/20 font-mono text-xs text-foreground"
                rows={8}
                value={additionalDataText}
                onChange={(event) => setAdditionalDataText(event.target.value)}
              />
            </label>
          </div>
        ) : (
          <pre className="max-h-64 overflow-auto rounded border border-white/10 bg-background/20 p-3 text-xs text-foreground/80">
            {additionalDataText.trim() ? additionalDataText : "{}"}
          </pre>
        )}
      </div>
      {toast ? <p className="mt-2 text-xs text-emerald-400">{toast}</p> : null}
      {errorMessage ? <p className="mt-2 text-xs text-danger">{errorMessage}</p> : null}
    </div>
  );
}

function AgentsPanel({ query }: { query: UseQueryResult<AgentSummary[]> }) {
  if (query.isLoading) return <LoadingState label="agents" />;
  if (query.isError) return <ErrorState error={query.error as Error} />;
  const list = query.data ?? [];
  if (!list.length) {
    return <div className="text-sm text-foreground/60">No agents found. Create agents from the network detail view.</div>;
  }
  return (
    <div className="space-y-4">
      {list.map((agent) => (
        <AgentCard key={agent.id} agent={agent} />
      ))}
    </div>
  );
}

function ToolsPanel({ query }: { query: UseQueryResult<ToolSummary[]> }) {
  if (query.isLoading) return <LoadingState label="tools" />;
  if (query.isError) return <ErrorState error={query.error as Error} />;
  const list = query.data ?? [];
  if (!list.length) {
    return <div className="text-sm text-foreground/60">No tools registered. Use the CLI or API to seed global tools.</div>;
  }
  return (
    <div className="space-y-4">
      {list.map((tool) => (
        <ToolCard key={tool.id} tool={tool} />
      ))}
    </div>
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
