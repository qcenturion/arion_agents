"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import {
  fetchAgents,
  fetchNetworks,
  fetchTools,
  fetchSnapshots,
  testTool,
  updateAgent,
  updateTool,
  type AgentUpdatePayload,
  type ToolTestPayload,
  type ToolUpdatePayload,
  type PublishNetworkPayload,
  compileAndPublishNetwork
} from "@/lib/api/config";
import type {
  AgentSummary,
  NetworkSummary,
  SnapshotSummary,
  ToolSummary,
  ToolTestResponse
} from "@/lib/api/types";

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

  const handlePublish = () => {
    setErrorMessage(null);
    setToast(null);
    mutation.mutate({ notes: "manual publish", published_by: "frontend" });
  };

  return (
    <div className="rounded border border-white/10 bg-background/30 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-foreground">{network.name}</h3>
          <p className="text-sm text-foreground/60">{network.description ?? "No description"}</p>
          <p className="mt-1 text-xs text-foreground/50">
            Active snapshot: {network.current_version_id ?? "unpublished"}
          </p>
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

function AgentCard({ agent }: { agent: AgentSummary }) {
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [displayName, setDisplayName] = useState(agent.display_name ?? "");
  const [description, setDescription] = useState(agent.description ?? "");
  const [allowRespond, setAllowRespond] = useState(agent.allow_respond);
  const [isDefault, setIsDefault] = useState(agent.is_default);
  const [promptTemplate, setPromptTemplate] = useState(agent.prompt_template ?? "");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    setDisplayName(agent.display_name ?? "");
    setDescription(agent.description ?? "");
    setAllowRespond(agent.allow_respond);
    setIsDefault(agent.is_default);
    setPromptTemplate(agent.prompt_template ?? "");
  }, [agent.display_name, agent.description, agent.allow_respond, agent.id, agent.is_default, agent.prompt_template]);

  const mutation = useMutation({
    mutationFn: (payload: AgentUpdatePayload) => updateAgent(agent.network_id, agent.id, payload),
    onSuccess: (data) => {
      setErrorMessage(null);
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      setDisplayName(data.display_name ?? "");
      setDescription(data.description ?? "");
      setAllowRespond(data.allow_respond);
      setIsDefault(data.is_default);
      setPromptTemplate(data.prompt_template ?? "");
      setIsEditing(false);
    },
    onError: (err) => {
      setErrorMessage(extractApiErrorMessage(err));
    }
  });

  const resetForm = () => {
    setDisplayName(agent.display_name ?? "");
    setDescription(agent.description ?? "");
    setAllowRespond(agent.allow_respond);
    setIsDefault(agent.is_default);
    setPromptTemplate(agent.prompt_template ?? "");
  };

  const handleCancel = () => {
    resetForm();
    setErrorMessage(null);
    setIsEditing(false);
  };

  const handleSave = () => {
    setErrorMessage(null);
    const payload: AgentUpdatePayload = {
      display_name: displayName,
      description,
      allow_respond: allowRespond,
      is_default: isDefault,
      prompt_template: promptTemplate ?? ""
    };
    mutation.mutate(payload);
  };

  const capabilityBadges = [
    { label: "Allow RESPOND", value: allowRespond ? "Yes" : "No" },
    { label: "Default agent", value: isDefault ? "Yes" : "No" }
  ];

  return (
    <article className="rounded border border-white/10 bg-background/30 p-4">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-foreground">{displayName.trim() ? displayName : agent.key}</h3>
          <p className="text-xs font-mono text-foreground/40">{agent.key}</p>
          <p className="mt-1 text-xs text-foreground/50">Network ID: {agent.network_id}</p>
        </div>
        <div className="flex gap-2">
          {isEditing ? (
            <>
              <button
                type="button"
                className="rounded border border-white/10 px-3 py-1 text-sm text-foreground/70 hover:border-white/30"
                onClick={handleCancel}
                disabled={mutation.isPending}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded bg-primary/80 px-3 py-1 text-sm text-background hover:bg-primary disabled:opacity-60"
                onClick={handleSave}
                disabled={mutation.isPending}
              >
                {mutation.isPending ? "Saving…" : "Save"}
              </button>
            </>
          ) : (
            <button
              type="button"
              className="rounded border border-white/10 px-3 py-1 text-sm text-foreground/70 hover:border-white/30"
              onClick={() => setIsEditing(true)}
            >
              Edit
            </button>
          )}
        </div>
      </header>

      <section className="mt-4 space-y-4">
        {isEditing ? (
          <div className="space-y-4">
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Display name</label>
              <input
                className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="Friendly name shown in the UI"
              />
            </div>
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Description</label>
              <textarea
                className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                rows={3}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="High-level summary of this agent's role"
              />
              <p className="mt-1 text-xs text-foreground/50">Shown to other agents when deciding whether to route here.</p>
            </div>
            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-sm text-foreground/80">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-white/20 bg-background"
                  checked={allowRespond}
                  onChange={(event) => setAllowRespond(event.target.checked)}
                />
                Allow RESPOND
              </label>
              <label className="flex items-center gap-2 text-sm text-foreground/80">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-white/20 bg-background"
                  checked={isDefault}
                  onChange={(event) => setIsDefault(event.target.checked)}
                />
                Default agent
              </label>
            </div>
            <p className="text-xs text-foreground/50">Default agents must retain RESPOND permission; constraint checks run on save.</p>
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Prompt template</label>
              <textarea
                className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                rows={8}
                value={promptTemplate}
                onChange={(event) => setPromptTemplate(event.target.value)}
                placeholder="Base instructions for this agent"
              />
              <p className="mt-1 text-xs text-foreground/50">
                Runtime automatically appends conversation context, constraint rules, equipped tool definitions, and route options after this template.
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-foreground/60">{description.trim() ? description : "No description."}</p>
            <div className="flex flex-wrap gap-3 text-xs text-foreground/70">
              {capabilityBadges.map((item) => (
                <span key={item.label} className="rounded border border-white/10 bg-background/60 px-2 py-1">
                  <span className="font-semibold text-foreground">{item.label}:</span> {item.value}
                </span>
              ))}
            </div>
            <div>
              <h4 className="text-xs uppercase tracking-wide text-foreground/50">Prompt template</h4>
              <pre className="mt-2 whitespace-pre-wrap rounded border border-white/10 bg-background/50 p-3 text-sm text-foreground/80">
                {promptTemplate?.trim() ? promptTemplate : "—"}
              </pre>
              <p className="mt-1 text-xs text-foreground/50">
                Context, constraint, tool, and route sections are appended automatically during execution.
              </p>
            </div>
          </div>
        )}

        <div>
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
            <p className="mt-2 text-xs text-foreground/50">No tools equipped.</p>
          )}
        </div>

        <div>
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
            <p className="mt-2 text-xs text-foreground/50">No downstream routes configured.</p>
          )}
        </div>
      </section>

      {errorMessage ? <p className="mt-3 text-sm text-danger">{errorMessage}</p> : null}
    </article>
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

function ToolCard({ tool }: { tool: ToolSummary }) {
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [displayName, setDisplayName] = useState(tool.display_name ?? "");
  const [description, setDescription] = useState(tool.description ?? "");
  const [providerType, setProviderType] = useState(tool.provider_type ?? "");
  const [secretRef, setSecretRef] = useState(tool.secret_ref ?? "");
  const [paramsSchemaText, setParamsSchemaText] = useState(prettyJson(tool.params_schema));
  const [additionalDataText, setAdditionalDataText] = useState(prettyJson(tool.additional_data));
  const [editError, setEditError] = useState<string | null>(null);

  const [testParamsText, setTestParamsText] = useState("{}");
  const [testSystemParamsText, setTestSystemParamsText] = useState("{}");
  const [testAdditionalDataText, setTestAdditionalDataText] = useState("{}");
  const [testResult, setTestResult] = useState<ToolTestResponse | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  useEffect(() => {
    setDisplayName(tool.display_name ?? "");
    setDescription(tool.description ?? "");
    setProviderType(tool.provider_type ?? "");
    setSecretRef(tool.secret_ref ?? "");
    setParamsSchemaText(prettyJson(tool.params_schema));
    setAdditionalDataText(prettyJson(tool.additional_data));
    setTestParamsText("{}");
    setTestSystemParamsText("{}");
    setTestAdditionalDataText("{}");
    setTestResult(null);
    setTestError(null);
  }, [tool.additional_data, tool.description, tool.display_name, tool.id, tool.params_schema, tool.provider_type, tool.secret_ref]);

  const mutation = useMutation({
    mutationFn: (payload: ToolUpdatePayload) => updateTool(tool.id, payload),
    onSuccess: (data) => {
      setEditError(null);
      queryClient.invalidateQueries({ queryKey: ["tools"] });
      setDisplayName(data.display_name ?? "");
      setDescription(data.description ?? "");
      setProviderType(data.provider_type ?? "");
      setSecretRef(data.secret_ref ?? "");
      setParamsSchemaText(prettyJson(data.params_schema));
      setAdditionalDataText(prettyJson(data.additional_data));
      setIsEditing(false);
    },
    onError: (err) => {
      setEditError(extractApiErrorMessage(err));
    }
  });

  const testMutation = useMutation({
    mutationFn: (payload: ToolTestPayload) => testTool(tool.id, payload),
    onSuccess: (data) => {
      setTestError(null);
      setTestResult(data);
    },
    onError: (err) => {
      setTestResult(null);
      setTestError(extractApiErrorMessage(err));
    }
  });

  const resetEditState = () => {
    setDisplayName(tool.display_name ?? "");
    setDescription(tool.description ?? "");
    setProviderType(tool.provider_type ?? "");
    setSecretRef(tool.secret_ref ?? "");
    setParamsSchemaText(prettyJson(tool.params_schema));
    setAdditionalDataText(prettyJson(tool.additional_data));
    setEditError(null);
  };

  const handleCancel = () => {
    resetEditState();
    setIsEditing(false);
  };

  const handleSave = () => {
    const paramsResult = parseJsonObject(paramsSchemaText, "Params schema");
    if (!paramsResult.ok) {
      setEditError(paramsResult.message);
      return;
    }
    const metadataResult = parseJsonObject(additionalDataText, "Additional data");
    if (!metadataResult.ok) {
      setEditError(metadataResult.message);
      return;
    }
    setEditError(null);
    const payload: ToolUpdatePayload = {
      display_name: displayName,
      description,
      provider_type: providerType,
      secret_ref: secretRef,
      params_schema: paramsResult.value,
      additional_data: metadataResult.value
    };
    mutation.mutate(payload);
  };

  const handleTest = () => {
    const paramsResult = parseJsonObject(testParamsText, "Params");
    if (!paramsResult.ok) {
      setTestError(paramsResult.message);
      setTestResult(null);
      return;
    }
    const systemResult = parseJsonObject(testSystemParamsText, "System params");
    if (!systemResult.ok) {
      setTestError(systemResult.message);
      setTestResult(null);
      return;
    }
    const overrideResult = parseJsonObjectOptional(testAdditionalDataText, "Additional data override");
    if (!overrideResult.ok) {
      setTestError(overrideResult.message);
      setTestResult(null);
      return;
    }
    setTestError(null);
    const payload: ToolTestPayload = {
      params: paramsResult.value,
      system_params: systemResult.value,
      additional_data_override: overrideResult.value
    };
    testMutation.mutate(payload);
  };

  const schemaHelp = "Tool metadata must include agent_params_json_schema so agents get JSON schema guidance.";

  return (
    <article className="rounded border border-white/10 bg-background/30 p-4">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-foreground">{displayName.trim() ? displayName : tool.key}</h3>
          <p className="text-xs font-mono text-foreground/40">{tool.key}</p>
        </div>
        <div className="flex gap-2">
          {isEditing ? (
            <>
              <button
                type="button"
                className="rounded border border-white/10 px-3 py-1 text-sm text-foreground/70 hover:border-white/30"
                onClick={handleCancel}
                disabled={mutation.isPending}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded bg-primary/80 px-3 py-1 text-sm text-background hover:bg-primary disabled:opacity-60"
                onClick={handleSave}
                disabled={mutation.isPending}
              >
                {mutation.isPending ? "Saving…" : "Save"}
              </button>
            </>
          ) : (
            <button
              type="button"
              className="rounded border border-white/10 px-3 py-1 text-sm text-foreground/70 hover:border-white/30"
              onClick={() => setIsEditing(true)}
            >
              Edit
            </button>
          )}
        </div>
      </header>

      <section className="mt-4 space-y-4">
        {isEditing ? (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Display name</label>
                <input
                  className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="Friendly tool name"
                />
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Provider type</label>
                <input
                  className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                  value={providerType}
                  onChange={(event) => setProviderType(event.target.value)}
                  placeholder="e.g. builtin:http"
                />
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Secret ref</label>
                <input
                  className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                  value={secretRef}
                  onChange={(event) => setSecretRef(event.target.value)}
                  placeholder="Optional secret identifier"
                />
              </div>
            </div>
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Description</label>
              <textarea
                className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                rows={3}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="What this tool does"
              />
            </div>
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Params schema</label>
              <textarea
                className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 font-mono text-xs text-foreground outline-none focus:border-primary"
                rows={8}
                value={paramsSchemaText}
                onChange={(event) => setParamsSchemaText(event.target.value)}
                placeholder="JSON describing agent-facing params"
              />
              <p className="mt-1 text-xs text-foreground/50">{schemaHelp}</p>
            </div>
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Additional data</label>
              <textarea
                className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 font-mono text-xs text-foreground outline-none focus:border-primary"
                rows={8}
                value={additionalDataText}
                onChange={(event) => setAdditionalDataText(event.target.value)}
                placeholder="Provider configuration, metadata, etc."
              />
            </div>
          </div>
        ) : (
          <div className="space-y-4 text-sm text-foreground/70">
            <p>{description.trim() ? description : "No description provided."}</p>
            <div className="grid gap-2 text-xs sm:grid-cols-2">
              <div>
                <span className="font-semibold text-foreground">Provider:</span> {providerType || "—"}
              </div>
              <div>
                <span className="font-semibold text-foreground">Secret ref:</span> {secretRef || "—"}
              </div>
            </div>
            <div>
              <h4 className="text-xs uppercase tracking-wide text-foreground/50">Params schema</h4>
              <pre className="mt-2 whitespace-pre-wrap rounded border border-white/10 bg-background/50 p-3 text-xs text-foreground/80">
                {paramsSchemaText.trim() ? paramsSchemaText : "{}"}
              </pre>
            </div>
            <div>
              <h4 className="text-xs uppercase tracking-wide text-foreground/50">Additional data</h4>
              <pre className="mt-2 whitespace-pre-wrap rounded border border-white/10 bg-background/50 p-3 text-xs text-foreground/80">
                {additionalDataText.trim() ? additionalDataText : "{}"}
              </pre>
            </div>
          </div>
        )}

        <div className="rounded border border-white/5 bg-background/40 p-4">
          <h4 className="text-sm font-semibold text-foreground">Test tool</h4>
          <p className="mt-1 text-xs text-foreground/60">
            Provide params and optional overrides, then execute the configured provider to debug quickly.
          </p>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <div className="md:col-span-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Params</label>
              <textarea
                className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 font-mono text-xs text-foreground outline-none focus:border-primary"
                rows={6}
                value={testParamsText}
                onChange={(event) => setTestParamsText(event.target.value)}
              />
            </div>
            <div className="md:col-span-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">System params</label>
              <textarea
                className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 font-mono text-xs text-foreground outline-none focus:border-primary"
                rows={6}
                value={testSystemParamsText}
                onChange={(event) => setTestSystemParamsText(event.target.value)}
              />
            </div>
            <div className="md:col-span-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Additional data override</label>
              <textarea
                className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 font-mono text-xs text-foreground outline-none focus:border-primary"
                rows={6}
                value={testAdditionalDataText}
                onChange={(event) => setTestAdditionalDataText(event.target.value)}
                placeholder="Optional runtime metadata override"
              />
            </div>
          </div>
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              className="rounded bg-primary/80 px-3 py-1 text-sm text-background hover:bg-primary disabled:opacity-60"
              onClick={handleTest}
              disabled={testMutation.isPending}
            >
              {testMutation.isPending ? "Testing…" : "Test tool"}
            </button>
            {testResult ? (
              <span className={`text-xs ${testResult.ok ? "text-emerald-400" : "text-danger"}`}>
                Status {testResult.status}{testResult.ok ? " (ok)" : " (error)"}
              </span>
            ) : null}
          </div>
          {testError ? <p className="mt-2 text-xs text-danger">{testError}</p> : null}
          {testResult ? (
            <pre className="mt-3 whitespace-pre-wrap rounded border border-white/10 bg-background/50 p-3 text-xs text-foreground/80">
              {testResult.ok
                ? prettyJson(testResult.result ?? {})
                : testResult.error ?? "Unknown error"}
            </pre>
          ) : null}
        </div>
      </section>

      {editError ? <p className="mt-3 text-sm text-danger">{editError}</p> : null}
    </article>
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

type ApiError = Error & { status?: number; body?: unknown };

function extractApiErrorMessage(error: unknown): string {
  if (!error || typeof error !== "object") {
    return "Request failed";
  }
  const err = error as ApiError;
  const body = err.body as { detail?: unknown } | undefined;
  const detail = body?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (detail && typeof detail === "object") {
    const maybe = detail as { message?: unknown };
    if (typeof maybe.message === "string") {
      return maybe.message;
    }
  }
  if (err.message) {
    return err.message;
  }
  if (typeof err.status === "number") {
    return `Request failed with status ${err.status}`;
  }
  return "Request failed";
}

type ParseResult = { ok: true; value: Record<string, unknown> } | { ok: false; message: string };

function parseJsonObject(text: string, label: string): ParseResult {
  if (!text.trim()) {
    return { ok: true, value: {} };
  }
  try {
    const parsed = JSON.parse(text);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { ok: false, message: `${label} must be a JSON object` };
    }
    return { ok: true, value: parsed as Record<string, unknown> };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, message: `${label} JSON is invalid: ${message}` };
  }
}

function parseJsonObjectOptional(text: string, label: string): { ok: true; value?: Record<string, unknown> } | { ok: false; message: string } {
  if (!text.trim()) {
    return { ok: true, value: undefined };
  }
  const result = parseJsonObject(text, label);
  if (!result.ok) {
    return result;
  }
  return { ok: true, value: result.value };
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return `/* failed to render JSON: ${message} */`;
  }
}
