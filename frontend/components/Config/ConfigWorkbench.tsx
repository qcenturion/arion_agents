"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";

import { AgentCard, ErrorState, LoadingState, ToolCard, extractApiErrorMessage, parseJsonObject, prettyJson } from "@/components/Config/shared";
import {
  fetchAgents,
  fetchNetworks,
  fetchTools,
  fetchSnapshots,
  fetchNetworkGraph,
  createNetwork,
  createAgent,
  createTool,
  duplicateAgent,
  duplicateNetwork,
  duplicateTool,
  type PublishNetworkPayload,
  compileAndPublishNetwork,
  updateNetwork,
  type NetworkUpdatePayload
} from "@/lib/api/config";
import type {
  AgentSummary,
  NetworkGraphTool,
  NetworkSummary,
  SnapshotSummary,
  ToolSummary
} from "@/lib/api/types";

const TABS = [
  { id: "networks", label: "Networks" },
  { id: "agents", label: "Agents" },
  { id: "tools", label: "Tools" },
  { id: "snapshots", label: "Snapshots" }
] as const;

type TabId = (typeof TABS)[number]["id"];

type ExecutionLogFieldConfigInput = {
  path: string;
  label?: string;
  max_chars?: number | null;
};

type ExecutionLogToolConfigInput = {
  request?: ExecutionLogFieldConfigInput[];
  response?: ExecutionLogFieldConfigInput[];
  request_max_chars?: number | null;
  response_max_chars?: number | null;
};

type ExecutionLogPolicyInput = {
  defaults?: {
    request_max_chars?: number | null;
    response_max_chars?: number | null;
  };
  tools?: Record<string, ExecutionLogToolConfigInput>;
};

type ExecutionLogFieldDraft = {
  path: string;
  label: string;
  max_chars: string;
};

type ExecutionLogToolDraft = {
  key: string;
  request_max_chars: string;
  response_max_chars: string;
  request: ExecutionLogFieldDraft[];
  response: ExecutionLogFieldDraft[];
};

type ExecutionLogPolicyDraft = {
  defaults: {
    request_max_chars: string;
    response_max_chars: string;
  };
  tools: ExecutionLogToolDraft[];
};

type FieldSide = "request" | "response";

type ExecutionLogToolOption = {
  key: string;
  label: string;
  requestFieldOptions: string[];
  responseFieldOptions: string[];
};

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
        {tab === "networks" ? <NetworksPanel networksQuery={networksQuery} agentsQuery={agentsQuery} /> : null}
        {tab === "agents" ? <AgentsPanel agentsQuery={agentsQuery} networks={networksQuery.data ?? []} /> : null}
        {tab === "tools" ? <ToolsPanel query={toolsQuery} /> : null}
        {tab === "snapshots" ? <SnapshotsPanel query={snapshotsQuery} /> : null}
      </div>
    </div>
  );
}

function NetworksPanel({ networksQuery, agentsQuery }: { networksQuery: UseQueryResult<NetworkSummary[]>, agentsQuery: UseQueryResult<AgentSummary[]> }) {
  if (networksQuery.isLoading || agentsQuery.isLoading) return <LoadingState label="networks and agents" />;
  if (networksQuery.isError) return <ErrorState error={networksQuery.error as Error} />;
  if (agentsQuery.isError) return <ErrorState error={agentsQuery.error as Error} />;
  
  const networks = networksQuery.data ?? [];
  const agents = agentsQuery.data ?? [];

  return (
    <div className="space-y-3">
      <CreateNetworkCard existingNetworks={networks} />
      {networks.map((item) => (
        <NetworkRow key={item.id} network={item} agents={agents} allNetworks={networks} />
      ))}
    </div>
  );
}

function generateCloneName(base: string, networks: NetworkSummary[]): string {
  const trimmed = base.trim() || "New Network";
  const existing = new Set(networks.map((item) => item.name.trim().toLowerCase()));
  let candidate = `${trimmed} Copy`;
  let index = 2;
  while (existing.has(candidate.trim().toLowerCase())) {
    candidate = `${trimmed} Copy ${index}`;
    index += 1;
  }
  return candidate;
}

function NetworkRow({ network, agents, allNetworks }: { network: NetworkSummary, agents: AgentSummary[], allNetworks: NetworkSummary[] }) {
  const queryClient = useQueryClient();
  const [toast, setToast] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState(network.name);
  const [description, setDescription] = useState(network.description ?? "");
  const [status, setStatus] = useState(network.status ?? "draft");
  const [additionalDataText, setAdditionalDataText] = useState(prettyJson(network.additional_data ?? {}));
  const [forceRespond, setForceRespond] = useState(false);
  const [forceRespondAgent, setForceRespondAgent] = useState("");
  const [toolOptions, setToolOptions] = useState<ExecutionLogToolOption[]>([]);
  const [isFetchingTools, setIsFetchingTools] = useState(false);
  const [isCloning, setIsCloning] = useState(false);
  const [cloneName, setCloneName] = useState(() => generateCloneName(network.name, allNetworks));
  const [cloneDescription, setCloneDescription] = useState(network.description ?? "");
  const [cloneError, setCloneError] = useState<string | null>(null);

  const otherNetworkNames = useMemo(() => {
    return allNetworks
      .filter((item) => item.id !== network.id)
      .map((item) => item.name.trim().toLowerCase());
  }, [allNetworks, network.id]);

  const allNetworkNames = useMemo(
    () => allNetworks.map((item) => item.name.trim().toLowerCase()),
    [allNetworks]
  );

  const respondAgentOptions = useMemo(() => {
    return agents
      .filter((agent) => agent.network_id === network.id && agent.allow_respond)
      .sort((a, b) => a.key.localeCompare(b.key));
  }, [agents, network.id]);

  const parsedAdditionalData = useMemo<Record<string, unknown> | null>(() => {
    try {
      if (!additionalDataText.trim()) {
        return {};
      }
      const parsed = JSON.parse(additionalDataText);
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        return null;
      }
      return parsed as Record<string, unknown>;
    } catch {
      return null;
    }
  }, [additionalDataText]);

  const executionLogPolicyValue = useMemo<ExecutionLogPolicyInput | null>(() => {
    if (!parsedAdditionalData) {
      return null;
    }
    const policy = (parsedAdditionalData as Record<string, unknown>).execution_log;
    if (!policy || typeof policy !== "object" || Array.isArray(policy)) {
      return null;
    }
    return policy as ExecutionLogPolicyInput;
  }, [parsedAdditionalData]);

  const policyParseError = parsedAdditionalData === null;

  useEffect(() => {
    setName(network.name);
    setDescription(network.description ?? "");
    setStatus(network.status ?? "draft");
    const additionalData = network.additional_data ?? {};
    setAdditionalDataText(prettyJson(additionalData));
    setForceRespond(additionalData.force_respond === true);
    const savedAgentKey = additionalData.force_respond_agent ?? "";
    const isValid = respondAgentOptions.some(agent => agent.key === savedAgentKey);
    setForceRespondAgent(isValid ? savedAgentKey : "");
    setIsEditing(false);
    setToolOptions([]);
    setIsFetchingTools(false);
  }, [network.name, network.description, network.status, network.additional_data, respondAgentOptions]);

  useEffect(() => {
    if (!isCloning) {
      setCloneName(generateCloneName(network.name, allNetworks));
      setCloneDescription(network.description ?? "");
    }
    setCloneError(null);
  }, [isCloning, network.id, network.name, network.description, allNetworks]);

  useEffect(() => {
    let cancelled = false;
    async function loadTools() {
      try {
        setIsFetchingTools(true);
        setErrorMessage(null);
        const graph = await fetchNetworkGraph(network.id);
        if (cancelled) return;
        const options = (graph.tools ?? []).map((tool) => {
          const display = tool.display_name?.trim();
          const label = display ? `${display} (${tool.key})` : tool.key;
          const requestFieldOptions = inferRequestFieldOptions(tool);
          const responseFieldOptions = inferResponseFieldOptions(tool);
          return { key: tool.key, label, requestFieldOptions, responseFieldOptions };
        });
        setToolOptions(options);
      } catch (err) {
        if (!cancelled) {
          setToolOptions([]);
          setErrorMessage(extractApiErrorMessage(err));
        }
      } finally {
        if (!cancelled) {
          setIsFetchingTools(false);
        }
      }
    }
    if (isEditing) {
      loadTools();
    } else {
      setToolOptions([]);
      setIsFetchingTools(false);
    }
    return () => {
      cancelled = true;
    };
  }, [isEditing, network.id]);

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
      setName(data.name ?? name);
      setDescription(data.description ?? "");
      setStatus(data.status ?? "draft");
      const additionalData = data.additional_data ?? {};
      setAdditionalDataText(prettyJson(additionalData));
      setForceRespond(additionalData.force_respond === true);
      const savedAgentKey = additionalData.force_respond_agent ?? "";
      const isValid = respondAgentOptions.some(agent => agent.key === savedAgentKey);
      setForceRespondAgent(isValid ? savedAgentKey : "");
      queryClient.invalidateQueries({ queryKey: ["networks"] });
      setIsEditing(false);
      setToast("Network updated");
    },
    onError: (err) => {
      setToast(null);
      setErrorMessage(extractApiErrorMessage(err));
    }
  });

  const cloneMutation = useMutation({
    mutationFn: (payload: { name: string; description?: string | null }) => duplicateNetwork(network.id, payload),
    onSuccess: (data) => {
      setCloneError(null);
      setIsCloning(false);
      setToast(`Cloned network to '${data.name}'`);
      queryClient.invalidateQueries({ queryKey: ["networks"] });
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      queryClient.invalidateQueries({ queryKey: ["snapshots"] });
    },
    onError: (err) => {
      setToast(null);
      setCloneError(extractApiErrorMessage(err));
    }
  });

  const resetEditState = () => {
    setName(network.name);
    setDescription(network.description ?? "");
    setStatus(network.status ?? "draft");
    const additionalData = network.additional_data ?? {};
    setAdditionalDataText(prettyJson(additionalData));
    setForceRespond(additionalData.force_respond === true);
    const savedAgentKey = additionalData.force_respond_agent ?? "";
    const isValid = respondAgentOptions.some(agent => agent.key === savedAgentKey);
    setForceRespondAgent(isValid ? savedAgentKey : "");
    setIsEditing(false);
  };

  const handlePublish = () => {
    setErrorMessage(null);
    setToast(null);
    mutation.mutate({ notes: "manual publish", published_by: "frontend" });
  };

  const toggleClone = () => {
    if (isCloning) {
      setIsCloning(false);
      setCloneError(null);
      return;
    }
    setCloneName(generateCloneName(network.name, allNetworks));
    setCloneDescription(network.description ?? "");
    setCloneError(null);
    setToast(null);
    setIsCloning(true);
  };

  const handleCloneSubmit = () => {
    setCloneError(null);
    const trimmedName = cloneName.trim();
    if (!trimmedName) {
      setCloneError("Clone name is required");
      return;
    }
    if (allNetworkNames.includes(trimmedName.toLowerCase())) {
      setCloneError("Network name already exists");
      return;
    }
    const desc = cloneDescription.trim();
    cloneMutation.mutate({ name: trimmedName, description: desc ? desc : null });
  };

  const handleSave = () => {
    setErrorMessage(null);
    const trimmedName = name.trim();
    if (!trimmedName) {
      setErrorMessage("Network name is required");
      return;
    }
    if (otherNetworkNames.includes(trimmedName.toLowerCase())) {
      setErrorMessage("Network name already exists");
      return;
    }
    const parsed = parseJsonObject(additionalDataText, "Additional data");
    if (!parsed.ok) {
      setErrorMessage(parsed.message);
      return;
    }
    const additionalData = parsed.value;
    additionalData.force_respond = forceRespond;
    additionalData.force_respond_agent = forceRespondAgent;
    const payload: NetworkUpdatePayload = {
      name: trimmedName,
      description,
      status,
      additional_data: additionalData
    };
    updateMutation.mutate(payload);
  };

  const handleExecutionPolicyApply = (policy: ExecutionLogPolicyInput | null) => {
    if (policyParseError) {
      setErrorMessage("Fix Additional data JSON before applying execution log policy edits.");
      return;
    }
    setErrorMessage(null);
    const base: Record<string, unknown> = parsedAdditionalData ? { ...parsedAdditionalData } : {};
    if (policy && (policy.defaults || policy.tools)) {
      base.execution_log = policy;
    } else {
      delete base.execution_log;
    }
    setAdditionalDataText(prettyJson(base));
  };

  return (
    <div className="rounded border border-white/10 bg-background/30 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          {isEditing ? (
            <input
              className="w-full rounded border border-white/10 bg-background/20 px-2 py-1 text-base font-semibold text-foreground focus:border-primary focus:outline-none"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Network name"
            />
          ) : (
            <h3 className="text-base font-semibold text-foreground">{network.name}</h3>
          )}
          <p className="text-sm text-foreground/60">{description.trim() ? description : "No description"}</p>
          <p className="mt-1 text-xs text-foreground/50">Status: {status}</p>
          <p className="mt-1 text-xs text-foreground/50">Active snapshot: {network.current_version_id ?? "unpublished"}</p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded border border-white/10 px-3 py-1 text-sm text-foreground/70 hover:border-white/30 disabled:opacity-60"
            onClick={toggleClone}
            disabled={cloneMutation.isPending || mutation.isPending}
          >
            {cloneMutation.isPending ? "Cloning…" : isCloning ? "Close clone" : "Clone"}
          </button>
          <button
            type="button"
            className="rounded bg-primary/80 px-3 py-1 text-sm text-background hover:bg-primary disabled:opacity-60"
            onClick={handlePublish}
            disabled={mutation.isPending || isCloning}
          >
            {mutation.isPending ? "Publishing…" : "Publish network"}
          </button>
        </div>
      </div>
      <div className="mt-4 space-y-3">
        {isCloning ? (
          <div className="rounded border border-dashed border-white/10 bg-background/20 p-4">
            <h4 className="text-sm font-semibold text-foreground">Clone network</h4>
            <p className="mt-1 text-xs text-foreground/60">
              Creates a new draft network with copied agents, tools, routes, and RESPOND configuration.
            </p>
            <div className="mt-3 space-y-3">
              <label className="block text-xs font-medium text-foreground/70">
                Name
                <input
                  className="mt-1 w-full rounded border border-white/10 bg-background/20 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
                  value={cloneName}
                  onChange={(event) => setCloneName(event.target.value)}
                  placeholder="New network name"
                  disabled={cloneMutation.isPending}
                />
              </label>
              <label className="block text-xs font-medium text-foreground/70">
                Description (optional)
                <textarea
                  className="mt-1 w-full rounded border border-white/10 bg-background/20 p-2 text-sm text-foreground focus:border-primary focus:outline-none"
                  rows={2}
                  value={cloneDescription}
                  onChange={(event) => setCloneDescription(event.target.value)}
                  disabled={cloneMutation.isPending}
                  placeholder="Describe the cloned network"
                />
              </label>
            </div>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
                onClick={toggleClone}
                disabled={cloneMutation.isPending}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded bg-primary/80 px-3 py-1 text-xs text-background hover:bg-primary disabled:opacity-60"
                onClick={handleCloneSubmit}
                disabled={cloneMutation.isPending}
              >
                {cloneMutation.isPending ? "Cloning…" : "Create clone"}
              </button>
            </div>
            {cloneError ? <p className="mt-2 text-xs text-danger">{cloneError}</p> : null}
          </div>
        ) : null}
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
            <div className="space-y-2 rounded border border-white/10 bg-background/20 p-3">
              <h5 className="text-xs font-semibold uppercase tracking-wide text-foreground/70">Force Respond</h5>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 text-xs font-medium text-foreground/70">
                  <input
                    type="checkbox"
                    className="rounded border-white/10 bg-background/20 text-primary focus:ring-primary"
                    checked={forceRespond}
                    onChange={(event) => setForceRespond(event.target.checked)}
                  />
                  Enable
                </label>
                {forceRespond ? (
                  <label className="flex-1 text-xs font-medium text-foreground/70">
                    Agent
                    <select
                      className="mt-1 w-full rounded border border-white/10 bg-background/20 p-2 text-sm text-foreground"
                      value={forceRespondAgent}
                      onChange={(event) => setForceRespondAgent(event.target.value)}
                    >
                      <option value="">Select agent...</option>
                      {respondAgentOptions.map((agent) => (
                        <option key={agent.key} value={agent.key}>
                          {agent.display_name ? `${agent.display_name} (${agent.key})` : agent.key}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
              </div>
            </div>
            <ExecutionLogPolicyEditor
              policy={executionLogPolicyValue}
              onApply={handleExecutionPolicyApply}
              disabled={updateMutation.isPending}
              parseError={policyParseError}
              toolOptions={toolOptions}
              isLoadingTools={isFetchingTools}
            />
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

function CreateNetworkCard({ existingNetworks }: { existingNetworks: NetworkSummary[] }) {
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [respondSchemaText, setRespondSchemaText] = useState("");
  const [additionalDataText, setAdditionalDataText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setError(null);
    }
  }, [isOpen]);

  const mutation = useMutation({
    mutationFn: (payload: { name: string; description?: string | null; additional_data: Record<string, unknown> }) =>
      createNetwork(payload),
    onSuccess: (data) => {
      setToast(`Created network '${data.name}'`);
      setError(null);
      setName("");
      setDescription("");
      setRespondSchemaText("");
      setAdditionalDataText("");
      setIsOpen(false);
      queryClient.invalidateQueries({ queryKey: ["networks"] });
    },
    onError: (err) => {
      setToast(null);
      setError(extractApiErrorMessage(err));
    }
  });

  const handleSubmit = () => {
    setError(null);
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("Network name is required");
      return;
    }
    const lower = trimmedName.toLowerCase();
    if (existingNetworks.some((item) => item.name.trim().toLowerCase() === lower)) {
      setError("Network name already exists");
      return;
    }

    let respondSchema: Record<string, unknown> | null = null;
    if (respondSchemaText.trim()) {
      const schemaResult = parseJsonObject(respondSchemaText, "RESPOND payload schema");
      if (!schemaResult.ok) {
        setError(schemaResult.message);
        return;
      }
      respondSchema = schemaResult.value;
    }

    const additionalResult = parseJsonObject(additionalDataText, "Additional data");
    if (!additionalResult.ok) {
      setError(additionalResult.message);
      return;
    }

    const additionalPayload: Record<string, unknown> = { ...additionalResult.value };
    if (respondSchema) {
      additionalPayload.respond_payload_schema = respondSchema;
    }

    const desc = description.trim();

    mutation.mutate({
      name: trimmedName,
      description: desc ? desc : null,
      additional_data: additionalPayload
    });
  };

  return (
    <div className="rounded border border-dashed border-white/10 bg-background/20 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-foreground/70">Create network</h3>
          <p className="mt-1 text-xs text-foreground/60">Define network metadata and optional RESPOND payload schema.</p>
        </div>
        <button
          type="button"
          className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30"
          onClick={() => {
            setIsOpen((prev) => !prev);
            setToast(null);
            setError(null);
          }}
          disabled={mutation.isPending}
        >
          {isOpen ? "Close" : "New network"}
        </button>
      </div>
      {isOpen ? (
        <div className="mt-4 space-y-3">
          <label className="block text-xs font-medium text-foreground/70">
            Name
            <input
              className="mt-1 w-full rounded border border-white/10 bg-background/30 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Unique network name"
              disabled={mutation.isPending}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            Description (optional)
            <textarea
              className="mt-1 w-full rounded border border-white/10 bg-background/30 p-2 text-sm text-foreground focus:border-primary focus:outline-none"
              rows={2}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              disabled={mutation.isPending}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            RESPOND payload schema JSON (optional)
            <textarea
              className="mt-1 w-full rounded border border-white/10 bg-background/30 p-2 font-mono text-xs text-foreground focus:border-primary focus:outline-none"
              rows={4}
              value={respondSchemaText}
              onChange={(event) => setRespondSchemaText(event.target.value)}
              placeholder="{}"
              disabled={mutation.isPending}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            Additional data JSON (optional)
            <textarea
              className="mt-1 w-full rounded border border-white/10 bg-background/30 p-2 font-mono text-xs text-foreground focus:border-primary focus:outline-none"
              rows={4}
              value={additionalDataText}
              onChange={(event) => setAdditionalDataText(event.target.value)}
              placeholder="{}"
              disabled={mutation.isPending}
            />
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
              onClick={handleSubmit}
              disabled={mutation.isPending}
            >
              {mutation.isPending ? "Creating…" : "Create network"}
            </button>
            <button
              type="button"
              className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
              onClick={() => {
                setName("");
                setDescription("");
                setRespondSchemaText("");
                setAdditionalDataText("");
                setError(null);
              }}
              disabled={mutation.isPending}
            >
              Reset
            </button>
          </div>
          {error ? <p className="text-xs text-danger">{error}</p> : null}
        </div>
      ) : null}
      {toast ? <p className="mt-2 text-xs text-emerald-400">{toast}</p> : null}
    </div>
  );
}

function AgentsPanel({ agentsQuery, networks }: { agentsQuery: UseQueryResult<AgentSummary[]>, networks: NetworkSummary[] }) {
  if (agentsQuery.isLoading) return <LoadingState label="agents" />;
  if (agentsQuery.isError) return <ErrorState error={agentsQuery.error as Error} />;
  const list = agentsQuery.data ?? [];
  return (
    <div className="space-y-4">
      <CreateAgentCard networks={networks} existingAgents={list} />
      {list.length ? (
        list.map((agent) => <AgentCard key={agent.id} agent={agent} />)
      ) : (
        <div className="rounded border border-white/10 bg-background/20 p-4 text-sm text-foreground/60">
          No agents yet. Create an agent to start configuring your network.
        </div>
      )}
    </div>
  );
}

function CreateAgentCard({ networks, existingAgents }: { networks: NetworkSummary[], existingAgents: AgentSummary[] }) {
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const [networkId, setNetworkId] = useState<number | null>(networks[0]?.id ?? null);
  const [agentKey, setAgentKey] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [allowRespond, setAllowRespond] = useState(true);
  const [isDefault, setIsDefault] = useState(false);
  const [promptTemplate, setPromptTemplate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!networks.length) {
      setNetworkId(null);
      return;
    }
    setNetworkId((prev) => {
      if (prev && networks.some((item) => item.id === prev)) {
        return prev;
      }
      return networks[0]?.id ?? null;
    });
  }, [networks]);

  const mutation = useMutation({
    mutationFn: ({ networkId: id, payload }: { networkId: number; payload: { key: string; display_name?: string | null; description?: string | null; allow_respond: boolean; is_default: boolean; prompt_template?: string | null } }) =>
      createAgent(id, payload),
    onSuccess: (data) => {
      setToast(`Created agent '${data.key}'`);
      setError(null);
      setAgentKey("");
      setDisplayName("");
      setDescription("");
      setAllowRespond(true);
      setIsDefault(false);
      setPromptTemplate("");
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      queryClient.invalidateQueries({ queryKey: ["networks"] });
    },
    onError: (err) => {
      setToast(null);
      setError(extractApiErrorMessage(err));
    }
  });

  const handleSubmit = () => {
    setError(null);
    if (!networkId) {
      setError("Select a network");
      return;
    }
    const trimmedKey = agentKey.trim();
    if (!trimmedKey) {
      setError("Agent key is required");
      return;
    }
    const lowerKey = trimmedKey.toLowerCase();
    const existingKeys = existingAgents
      .filter((agent) => agent.network_id === networkId)
      .map((agent) => agent.key.toLowerCase());
    if (existingKeys.includes(lowerKey)) {
      setError("Agent key already exists in this network");
      return;
    }

    const payload = {
      key: trimmedKey,
      display_name: displayName.trim() ? displayName.trim() : null,
      description: description.trim() ? description.trim() : null,
      allow_respond: allowRespond,
      is_default: isDefault,
      prompt_template: promptTemplate.trim() ? promptTemplate : null
    };

    mutation.mutate({ networkId, payload });
  };

  const disableForm = mutation.isPending || !networks.length;

  return (
    <div className="rounded border border-dashed border-white/10 bg-background/20 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-foreground/70">Create agent</h3>
          <p className="mt-1 text-xs text-foreground/60">Agents belong to a network and can carry a prompt template.</p>
        </div>
        <button
          type="button"
          className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30"
          onClick={() => {
            setIsOpen((prev) => !prev);
            setToast(null);
            setError(null);
          }}
          disabled={disableForm}
        >
          {isOpen ? "Close" : "New agent"}
        </button>
      </div>
      {isOpen ? (
        <div className="mt-4 space-y-3">
          {networks.length ? (
            <label className="block text-xs font-medium text-foreground/70">
              Network
              <select
                className="mt-1 w-full rounded border border-white/10 bg-background/30 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
                value={networkId ?? ""}
                onChange={(event) => setNetworkId(Number(event.target.value) || null)}
                disabled={disableForm}
              >
                {networks.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <p className="text-xs text-foreground/60">Create a network first.</p>
          )}
          <label className="block text-xs font-medium text-foreground/70">
            Key
            <input
              className="mt-1 w-full rounded border border-white/10 bg-background/30 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              value={agentKey}
              onChange={(event) => setAgentKey(event.target.value)}
              placeholder="Unique agent key"
              disabled={disableForm}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            Display name (optional)
            <input
              className="mt-1 w-full rounded border border-white/10 bg-background/30 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              disabled={disableForm}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            Description (optional)
            <textarea
              className="mt-1 w-full rounded border border-white/10 bg-background/30 p-2 text-sm text-foreground focus:border-primary focus:outline-none"
              rows={2}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              disabled={disableForm}
            />
          </label>
          <div className="flex flex-wrap gap-4 text-xs text-foreground/70">
            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={allowRespond}
                onChange={(event) => setAllowRespond(event.target.checked)}
                disabled={disableForm}
              />
              Allow RESPOND
            </label>
            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={isDefault}
                onChange={(event) => setIsDefault(event.target.checked)}
                disabled={disableForm}
              />
              Default agent
            </label>
          </div>
          <label className="block text-xs font-medium text-foreground/70">
            Prompt template (optional)
            <textarea
              className="mt-1 w-full rounded border border-white/10 bg-background/30 p-2 font-mono text-xs text-foreground focus:border-primary focus:outline-none"
              rows={4}
              value={promptTemplate}
              onChange={(event) => setPromptTemplate(event.target.value)}
              disabled={disableForm}
            />
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
              onClick={handleSubmit}
              disabled={disableForm || !networks.length}
            >
              {mutation.isPending ? "Creating…" : "Create agent"}
            </button>
            <button
              type="button"
              className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
              onClick={() => {
                setAgentKey("");
                setDisplayName("");
                setDescription("");
                setAllowRespond(true);
                setIsDefault(false);
                setPromptTemplate("");
                setError(null);
              }}
              disabled={disableForm}
            >
              Reset
            </button>
          </div>
          {error ? <p className="text-xs text-danger">{error}</p> : null}
        </div>
      ) : null}
      {toast ? <p className="mt-2 text-xs text-emerald-400">{toast}</p> : null}
    </div>
  );
}

function ToolsPanel({ query }: { query: UseQueryResult<ToolSummary[]> }) {
  if (query.isLoading) return <LoadingState label="tools" />;
  if (query.isError) return <ErrorState error={query.error as Error} />;
  const list = query.data ?? [];
  return (
    <div className="space-y-4">
      <CreateToolCard />
      {list.length ? (
        list.map((tool) => <ToolCard key={tool.id} tool={tool} />)
      ) : (
        <div className="rounded border border-white/10 bg-background/20 p-4 text-sm text-foreground/60">
          No tools registered yet. Create one to share across networks.
        </div>
      )}
    </div>
  );
}

function CreateToolCard() {
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const [keyValue, setKeyValue] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [providerType, setProviderType] = useState("");
  const [secretRef, setSecretRef] = useState("");
  const [paramsSchemaText, setParamsSchemaText] = useState(prettyJson({}));
  const defaultAdditional = useMemo(
    () =>
      prettyJson({
        agent_params_json_schema: {
          type: "object",
          properties: {},
          required: [],
          additionalProperties: false
        }
      }),
    []
  );
  const [additionalDataText, setAdditionalDataText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setError(null);
      return;
    }
    if (!additionalDataText) {
      setAdditionalDataText(defaultAdditional);
    }
  }, [isOpen, additionalDataText, defaultAdditional]);

  const mutation = useMutation({
    mutationFn: (payload: {
      key: string;
      display_name?: string | null;
      description?: string | null;
      provider_type?: string | null;
      params_schema?: Record<string, unknown>;
      secret_ref?: string | null;
      additional_data: Record<string, unknown>;
    }) => createTool(payload),
    onSuccess: (data) => {
      setToast(`Created tool '${data.key}'`);
      setError(null);
      setKeyValue("");
      setDisplayName("");
      setDescription("");
      setProviderType("");
      setSecretRef("");
      setParamsSchemaText(prettyJson({}));
      setAdditionalDataText(defaultAdditional);
      queryClient.invalidateQueries({ queryKey: ["tools"] });
    },
    onError: (err) => {
      setToast(null);
      setError(extractApiErrorMessage(err));
    }
  });

  const handleSubmit = () => {
    setError(null);
    const trimmedKey = keyValue.trim();
    if (!trimmedKey) {
      setError("Tool key is required");
      return;
    }

    const paramsResult = parseJsonObject(paramsSchemaText, "Params schema");
    if (!paramsResult.ok) {
      setError(paramsResult.message);
      return;
    }

    const additionalResult = parseJsonObject(additionalDataText, "Additional data");
    if (!additionalResult.ok) {
      setError(additionalResult.message);
      return;
    }

    const additionalPayload = additionalResult.value;
    const agentSchema = additionalPayload.agent_params_json_schema;
    if (!agentSchema || typeof agentSchema !== "object" || Array.isArray(agentSchema)) {
      setError("additional_data.agent_params_json_schema must be an object");
      return;
    }

    mutation.mutate({
      key: trimmedKey,
      display_name: displayName.trim() ? displayName.trim() : null,
      description: description.trim() ? description.trim() : null,
      provider_type: providerType.trim() ? providerType.trim() : null,
      params_schema: paramsResult.value,
      secret_ref: secretRef.trim() ? secretRef.trim() : null,
      additional_data: additionalPayload
    });
  };

  return (
    <div className="rounded border border-dashed border-white/10 bg-background/20 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-foreground/70">Create tool</h3>
          <p className="mt-1 text-xs text-foreground/60">Global tools can be attached to any network.</p>
        </div>
        <button
          type="button"
          className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30"
          onClick={() => {
            setIsOpen((prev) => !prev);
            setToast(null);
            setError(null);
          }}
          disabled={mutation.isPending}
        >
          {isOpen ? "Close" : "New tool"}
        </button>
      </div>
      {isOpen ? (
        <div className="mt-4 space-y-3">
          <label className="block text-xs font-medium text-foreground/70">
            Key
            <input
              className="mt-1 w-full rounded border border-white/10 bg-background/30 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              value={keyValue}
              onChange={(event) => setKeyValue(event.target.value)}
              placeholder="Unique tool key"
              disabled={mutation.isPending}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            Display name (optional)
            <input
              className="mt-1 w-full rounded border border-white/10 bg-background/30 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              disabled={mutation.isPending}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            Description (optional)
            <textarea
              className="mt-1 w-full rounded border border-white/10 bg-background/30 p-2 text-sm text-foreground focus:border-primary focus:outline-none"
              rows={2}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              disabled={mutation.isPending}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            Provider type (optional)
            <input
              className="mt-1 w-full rounded border border-white/10 bg-background/30 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              value={providerType}
              onChange={(event) => setProviderType(event.target.value)}
              disabled={mutation.isPending}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            Secret ref (optional)
            <input
              className="mt-1 w-full rounded border border-white/10 bg-background/30 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              value={secretRef}
              onChange={(event) => setSecretRef(event.target.value)}
              disabled={mutation.isPending}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            Params schema JSON
            <textarea
              className="mt-1 w-full rounded border border-white/10 bg-background/30 p-2 font-mono text-xs text-foreground focus:border-primary focus:outline-none"
              rows={4}
              value={paramsSchemaText}
              onChange={(event) => setParamsSchemaText(event.target.value)}
              placeholder="{}"
              disabled={mutation.isPending}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            Additional data JSON
            <textarea
              className="mt-1 w-full rounded border border-white/10 bg-background/30 p-2 font-mono text-xs text-foreground focus:border-primary focus:outline-none"
              rows={6}
              value={additionalDataText}
              onChange={(event) => setAdditionalDataText(event.target.value)}
              disabled={mutation.isPending}
            />
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
              onClick={handleSubmit}
              disabled={mutation.isPending}
            >
              {mutation.isPending ? "Creating…" : "Create tool"}
            </button>
            <button
              type="button"
              className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
              onClick={() => {
                setKeyValue("");
                setDisplayName("");
                setDescription("");
                setProviderType("");
                setSecretRef("");
                setParamsSchemaText(prettyJson({}));
                setAdditionalDataText(defaultAdditional);
                setError(null);
              }}
              disabled={mutation.isPending}
            >
              Reset
            </button>
          </div>
          {error ? <p className="text-xs text-danger">{error}</p> : null}
        </div>
      ) : null}
      {toast ? <p className="mt-2 text-xs text-emerald-400">{toast}</p> : null}
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

interface ExecutionLogPolicyEditorProps {
  policy: ExecutionLogPolicyInput | null;
  onApply: (policy: ExecutionLogPolicyInput | null) => void;
  disabled?: boolean;
  parseError: boolean;
  toolOptions: ExecutionLogToolOption[];
  isLoadingTools: boolean;
}

function ExecutionLogPolicyEditor({
  policy,
  onApply,
  disabled = false,
  parseError,
  toolOptions,
  isLoadingTools
}: ExecutionLogPolicyEditorProps) {
  const [draft, setDraft] = useState<ExecutionLogPolicyDraft>(() => policyToDraft(policy));
  const [newToolKey, setNewToolKey] = useState("");
  const [toolError, setToolError] = useState<string | null>(null);
  const policyKey = useMemo(() => JSON.stringify(policy ?? {}), [policy]);
  const availableToolOptions = useMemo(() => {
    const activeKeys = new Set(draft.tools.map((tool) => tool.key));
    return toolOptions.filter((option) => !activeKeys.has(option.key));
  }, [draft.tools, toolOptions]);

  useEffect(() => {
    if (availableToolOptions.length === 0) {
      setNewToolKey("");
    }
  }, [availableToolOptions.length]);

  useEffect(() => {
    setDraft(policyToDraft(policy));
    setNewToolKey("");
    setToolError(null);
  }, [policyKey]);

  const updateDefault = (field: keyof ExecutionLogPolicyDraft["defaults"]) => (event: ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setDraft((prev) => ({
      ...prev,
      defaults: {
        ...prev.defaults,
        [field]: normalizeNumberInput(value, prev.defaults[field])
      }
    }));
  };

  const updateToolValue = (index: number, updater: (tool: ExecutionLogToolDraft) => ExecutionLogToolDraft) => {
    setDraft((prev) => ({
      ...prev,
      tools: prev.tools.map((tool, idx) => (idx === index ? updater(cloneToolDraft(tool)) : tool))
    }));
  };

  const updateFieldValue = (toolIndex: number, side: FieldSide, fieldIndex: number, key: keyof ExecutionLogFieldDraft, value: string) => {
    updateToolValue(toolIndex, (tool) => {
      const list = side === "request" ? [...tool.request] : [...tool.response];
      const field = { ...list[fieldIndex] };
      if (key === "max_chars") {
        field.max_chars = normalizeNumberInput(value, field.max_chars);
      } else {
        field[key] = value;
      }
      list[fieldIndex] = field;
      if (side === "request") {
        tool.request = list;
      } else {
        tool.response = list;
      }
      return tool;
    });
  };

  const addField = (toolIndex: number, side: FieldSide, defaultPath?: string) => {
    updateToolValue(toolIndex, (tool) => {
      const list = side === "request" ? [...tool.request] : [...tool.response];
      const initialPath = defaultPath ?? "";
      list.push({ path: initialPath, label: "", max_chars: "" });
      if (side === "request") {
        tool.request = list;
      } else {
        tool.response = list;
      }
      return tool;
    });
  };

  const removeField = (toolIndex: number, side: FieldSide, fieldIndex: number) => {
    updateToolValue(toolIndex, (tool) => {
      const list = side === "request" ? [...tool.request] : [...tool.response];
      list.splice(fieldIndex, 1);
      if (side === "request") {
        tool.request = list;
      } else {
        tool.response = list;
      }
      return tool;
    });
  };

  const handleAddTool = () => {
    const trimmed = newToolKey.trim();
    if (!trimmed) {
      setToolError("Tool key is required");
      return;
    }
    if (!toolOptions.some((option) => option.key === trimmed)) {
      setToolError("Select a tool from the network list");
      return;
    }
    if (draft.tools.some((tool) => tool.key.trim().toLowerCase() === trimmed.toLowerCase())) {
      setToolError("Tool already configured");
      return;
    }
    setDraft((prev) => ({
      ...prev,
      tools: [
        ...prev.tools,
        { key: trimmed, request_max_chars: "", response_max_chars: "", request: [], response: [] }
      ]
    }));
    setNewToolKey("");
    setToolError(null);
  };

  const handleApply = () => {
    if (parseError) {
      return;
    }
    onApply(draftToPolicy(draft));
  };

  const handleClear = () => {
    setDraft(policyToDraft(null));
    setNewToolKey("");
    setToolError(null);
    onApply(null);
  };

  const handleReset = () => {
    setDraft(policyToDraft(policy));
    setNewToolKey("");
    setToolError(null);
  };

  const disableInputs = disabled || parseError || isLoadingTools;

  return (
    <div className="rounded border border-white/10 bg-background/20 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h5 className="text-xs font-semibold uppercase tracking-wide text-foreground/70">Execution log policy</h5>
          <p className="text-xs text-foreground/50">Control which tool payload slices are stored for this network.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
            onClick={handleReset}
            disabled={disableInputs}
          >
            Reset
          </button>
          <button
            type="button"
            className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
            onClick={handleClear}
            disabled={disableInputs}
          >
            Clear
          </button>
          <button
            type="button"
            className="rounded bg-primary/80 px-3 py-1 text-xs text-background hover:bg-primary disabled:opacity-60"
            onClick={handleApply}
            disabled={disableInputs}
          >
            Apply
          </button>
        </div>
      </div>
      {parseError ? (
        <p className="mt-3 text-xs text-danger">Invalid JSON detected. Fix Additional data JSON to edit execution log policy.</p>
      ) : (
        <div className="mt-3 space-y-4">
          <div>
            <h6 className="text-xs font-semibold text-foreground/70">Defaults</h6>
            <div className="mt-2 grid gap-3 sm:grid-cols-2">
              <label className="block text-xs text-foreground/60">
                Request max chars
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  className="mt-1 w-full rounded border border-white/10 bg-background/10 px-2 py-1 text-xs text-foreground disabled:opacity-60"
                  value={draft.defaults.request_max_chars}
                  onChange={updateDefault("request_max_chars")}
                  disabled={disableInputs}
                  placeholder="inherit (50)"
                />
                <p className="mt-1 text-[11px] text-foreground/45">
                  Controls how many characters of each tool request are shown when no specific fields are selected. Set to 0 to keep the full request text.
                </p>
              </label>
              <label className="block text-xs text-foreground/60">
                Response max chars
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  className="mt-1 w-full rounded border border-white/10 bg-background/10 px-2 py-1 text-xs text-foreground disabled:opacity-60"
                  value={draft.defaults.response_max_chars}
                  onChange={updateDefault("response_max_chars")}
                  disabled={disableInputs}
                  placeholder="inherit (100)"
                />
                <p className="mt-1 text-[11px] text-foreground/45">
                  Controls how many characters of each tool response are included in the log unless field rules override it. Set to 0 to keep the full response text.
                </p>
              </label>
            </div>
          </div>

          <div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h6 className="text-xs font-semibold text-foreground/70">Per-tool overrides</h6>
              <div className="flex gap-2">
                <select
                  value={newToolKey}
                  onChange={(event) => {
                    setNewToolKey(event.target.value);
                    setToolError(null);
                  }}
                  className="rounded border border-white/10 bg-background/10 px-2 py-1 text-xs text-foreground disabled:opacity-60"
                  disabled={disableInputs || availableToolOptions.length === 0}
                >
                  <option value="">Select tool…</option>
                  {availableToolOptions.map((option) => (
                    <option key={option.key} value={option.key}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="rounded border border-white/10 px-2 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
                  onClick={handleAddTool}
                  disabled={disableInputs || !newToolKey.trim()}
                >
                  Add tool
                </button>
              </div>
            </div>
            {isLoadingTools ? (
              <p className="mt-1 text-xs text-foreground/50">Loading tools…</p>
            ) : null}
            {toolError ? <p className="mt-1 text-xs text-danger">{toolError}</p> : null}
            <div className="mt-3 space-y-3">
              {draft.tools.length === 0 ? (
                <p className="text-xs text-foreground/50">No tool overrides configured.</p>
              ) : (
                draft.tools.map((tool, toolIndex) => (
                  <div key={`${tool.key}-${toolIndex}`} className="space-y-3 rounded border border-white/10 bg-background/10 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="text-xs text-foreground/70">
                        <span className="font-semibold">Tool</span>
                        <span className="ml-2 text-foreground/60">
                          {displayToolLabel(tool.key, toolOptions)}
                        </span>
                      </div>
                      <button
                        type="button"
                        className="rounded border border-white/10 px-2 py-1 text-xs text-danger/80 hover:border-white/30 disabled:opacity-60"
                        onClick={() =>
                          setDraft((prev) => ({
                            ...prev,
                            tools: prev.tools.filter((_, idx) => idx !== toolIndex)
                          }))
                        }
                        disabled={disableInputs}
                      >
                        Remove
                      </button>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="block text-xs text-foreground/60">
                        Request max chars
                        <input
                          type="text"
                          inputMode="numeric"
                          pattern="[0-9]*"
                          className="mt-1 w-full rounded border border-white/10 bg-background/20 px-2 py-1 text-xs text-foreground disabled:opacity-60"
                          value={tool.request_max_chars}
                          onChange={(event) => {
                            const value = event.target.value;
                            updateToolValue(toolIndex, (current) => ({
                              ...current,
                              request_max_chars: normalizeNumberInput(value, current.request_max_chars)
                            }));
                          }}
                          disabled={disableInputs}
                          placeholder="inherit"
                        />
                      </label>
                      <label className="block text-xs text-foreground/60">
                        Response max chars
                        <input
                          type="text"
                          inputMode="numeric"
                          pattern="[0-9]*"
                          className="mt-1 w-full rounded border border-white/10 bg-background/20 px-2 py-1 text-xs text-foreground disabled:opacity-60"
                          value={tool.response_max_chars}
                          onChange={(event) => {
                            const value = event.target.value;
                            updateToolValue(toolIndex, (current) => ({
                              ...current,
                              response_max_chars: normalizeNumberInput(value, current.response_max_chars)
                            }));
                          }}
                          disabled={disableInputs}
                          placeholder="inherit"
                        />
                      </label>
                    </div>

                    {(() => {
                      const optionDetails = toolOptions.find((option) => option.key === tool.key);
                      const requestSuggestions = optionDetails?.requestFieldOptions ?? [];
                      const responseSuggestions = optionDetails?.responseFieldOptions ?? [];
                      const nextRequestSuggestion = requestSuggestions.find((candidate) =>
                        !tool.request.some((field) => field.path === candidate)
                      );
                      const nextResponseSuggestion = responseSuggestions.find((candidate) =>
                        !tool.response.some((field) => field.path === candidate)
                      );

                      return (
                        <>
                          <ExecutionLogFieldList
                            title="Request fields"
                            fields={tool.request}
                            disabled={disableInputs}
                            suggestions={requestSuggestions}
                            onAdd={() => addField(toolIndex, "request", nextRequestSuggestion)}
                            onRemove={(fieldIndex) => removeField(toolIndex, "request", fieldIndex)}
                            onChange={(fieldIndex, key, value) => updateFieldValue(toolIndex, "request", fieldIndex, key, value)}
                          />
                          <ExecutionLogFieldList
                            title="Response fields"
                            fields={tool.response}
                            disabled={disableInputs}
                            suggestions={responseSuggestions}
                            onAdd={() => addField(toolIndex, "response", nextResponseSuggestion)}
                            onRemove={(fieldIndex) => removeField(toolIndex, "response", fieldIndex)}
                            onChange={(fieldIndex, key, value) => updateFieldValue(toolIndex, "response", fieldIndex, key, value)}
                          />
                        </>
                      );
                    })()}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface ExecutionLogFieldListProps {
  title: string;
  fields: ExecutionLogFieldDraft[];
  disabled: boolean;
  suggestions: string[];
  onAdd: () => void;
  onRemove: (index: number) => void;
  onChange: (index: number, key: keyof ExecutionLogFieldDraft, value: string) => void;
}

function ExecutionLogFieldList({ title, fields, disabled, suggestions, onAdd, onRemove, onChange }: ExecutionLogFieldListProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h6 className="text-xs font-semibold text-foreground/70">{title}</h6>
        <button
          type="button"
          className="rounded border border-white/10 px-2 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
          onClick={onAdd}
          disabled={disabled}
        >
          Add field
        </button>
      </div>
      {fields.length === 0 ? (
        <p className="text-xs text-foreground/50">No fields selected.</p>
      ) : (
        <div className="space-y-2">
          {fields.map((field, index) => (
            <div key={index} className="grid gap-2 sm:grid-cols-7">
              <div className="sm:col-span-3 flex flex-col gap-1">
                {suggestions.length > 0 ? (
                  <select
                    className="rounded border border-white/10 bg-background/20 px-2 py-1 text-xs text-foreground disabled:opacity-60"
                    value=""
                    onChange={(event) => {
                      const value = event.target.value;
                      if (value) {
                        onChange(index, "path", value);
                      }
                      event.currentTarget.selectedIndex = 0;
                    }}
                    disabled={disabled}
                  >
                    <option value="">Select field…</option>
                    {suggestions.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                ) : null}
                <input
                  type="text"
                  placeholder="path (e.g. result.value)"
                  className="rounded border border-white/10 bg-background/20 px-2 py-1 text-xs text-foreground disabled:opacity-60"
                  value={field.path}
                  onChange={(event) => onChange(index, "path", event.target.value)}
                  disabled={disabled}
                />
              </div>
              <input
                type="text"
                placeholder="label (optional)"
                className="sm:col-span-2 rounded border border-white/10 bg-background/20 px-2 py-1 text-xs text-foreground disabled:opacity-60"
                value={field.label}
                onChange={(event) => onChange(index, "label", event.target.value)}
                disabled={disabled}
              />
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                placeholder="max chars"
                className="rounded border border-white/10 bg-background/20 px-2 py-1 text-xs text-foreground disabled:opacity-60"
                value={field.max_chars}
                onChange={(event) => onChange(index, "max_chars", event.target.value)}
                disabled={disabled}
              />
              <button
                type="button"
                className="rounded border border-white/10 px-2 py-1 text-xs text-danger/80 hover:border-white/30 disabled:opacity-60"
                onClick={() => onRemove(index)}
                disabled={disabled}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function policyToDraft(policy: ExecutionLogPolicyInput | null): ExecutionLogPolicyDraft {
  const defaults = policy?.defaults ?? {};
  const tools = policy?.tools ?? {};
  return {
    defaults: {
      request_max_chars:
        defaults.request_max_chars === undefined || defaults.request_max_chars === null
          ? ""
          : String(defaults.request_max_chars),
      response_max_chars:
        defaults.response_max_chars === undefined || defaults.response_max_chars === null
          ? ""
          : String(defaults.response_max_chars)
    },
    tools: Object.entries(tools)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, cfg]) => ({
        key,
        request_max_chars:
          cfg.request_max_chars === undefined || cfg.request_max_chars === null
            ? ""
            : String(cfg.request_max_chars),
        response_max_chars:
          cfg.response_max_chars === undefined || cfg.response_max_chars === null
            ? ""
            : String(cfg.response_max_chars),
        request: (cfg.request ?? []).map((field) => ({
          path: field.path ?? "",
          label: field.label ?? "",
          max_chars:
            field.max_chars === undefined || field.max_chars === null ? "" : String(field.max_chars)
        })),
        response: (cfg.response ?? []).map((field) => ({
          path: field.path ?? "",
          label: field.label ?? "",
          max_chars:
            field.max_chars === undefined || field.max_chars === null ? "" : String(field.max_chars)
        }))
      }))
  };
}

function draftToPolicy(draft: ExecutionLogPolicyDraft): ExecutionLogPolicyInput | null {
  const defaults: NonNullable<ExecutionLogPolicyInput["defaults"]> = {};
  const requestDefault = parseNumberValue(draft.defaults.request_max_chars);
  if (requestDefault !== null) {
    defaults.request_max_chars = requestDefault;
  }
  const responseDefault = parseNumberValue(draft.defaults.response_max_chars);
  if (responseDefault !== null) {
    defaults.response_max_chars = responseDefault;
  }

  const tools: Record<string, ExecutionLogToolConfigInput> = {};
  draft.tools.forEach((tool) => {
    const key = tool.key.trim();
    if (!key) {
      return;
    }
    const config: ExecutionLogToolConfigInput = {};
    const requestLimit = parseNumberValue(tool.request_max_chars);
    if (requestLimit !== null) {
      config.request_max_chars = requestLimit;
    }
    const responseLimit = parseNumberValue(tool.response_max_chars);
    if (responseLimit !== null) {
      config.response_max_chars = responseLimit;
    }
    const requestFields = tool.request
      .map((field) => sanitizeFieldDraft(field))
      .filter((field): field is ExecutionLogFieldConfigInput => field !== null);
    if (requestFields.length > 0) {
      config.request = requestFields;
    }
    const responseFields = tool.response
      .map((field) => sanitizeFieldDraft(field))
      .filter((field): field is ExecutionLogFieldConfigInput => field !== null);
    if (responseFields.length > 0) {
      config.response = responseFields;
    }
    if (Object.keys(config).length > 0) {
      tools[key] = config;
    }
  });

  const result: ExecutionLogPolicyInput = {};
  if (Object.keys(defaults).length > 0) {
    result.defaults = defaults;
  }
  if (Object.keys(tools).length > 0) {
    result.tools = tools;
  }
  if (!result.defaults && !result.tools) {
    return null;
  }
  return result;
}

function sanitizeFieldDraft(field: ExecutionLogFieldDraft): ExecutionLogFieldConfigInput | null {
  const path = field.path.trim();
  if (!path) {
    return null;
  }
  const entry: ExecutionLogFieldConfigInput = { path };
  const label = field.label.trim();
  if (label) {
    entry.label = label;
  }
  const max = parseNumberValue(field.max_chars);
  if (max !== null) {
    entry.max_chars = max;
  }
  return entry;
}

function parseNumberValue(value: string): number | null {
  if (!value.trim()) {
    return null;
  }
  const parsed = Number(value.trim());
  if (!Number.isFinite(parsed)) {
    return null;
  }
  const normalized = Math.max(0, Math.floor(parsed));
  return normalized;
}

function normalizeNumberInput(value: string, previous: string): string {
  if (value === "") {
    return "";
  }
  if (/^\d+$/.test(value)) {
    return value;
  }
  return previous;
}

function cloneToolDraft(tool: ExecutionLogToolDraft): ExecutionLogToolDraft {
  return {
    ...tool,
    request: tool.request.map((field) => ({ ...field })),
    response: tool.response.map((field) => ({ ...field }))
  };
}

function displayToolLabel(key: string, options: ExecutionLogToolOption[]): string {
  const match = options.find((option) => option.key === key);
  return match ? match.label : key;
}

function inferRequestFieldOptions(tool: NetworkGraphTool): string[] {
  const collected: string[] = [];
  const schema = tool.params_schema as Record<string, unknown> | undefined;
  if (schema) {
    Object.entries(schema).forEach(([name, spec]) => {
      if (!name) return;
      if (typeof spec === "object" && spec !== null) {
        const source = (spec as Record<string, unknown>).source ?? "agent";
        if (source !== "system") {
          collected.push(name);
        }
      } else {
        collected.push(name);
      }
    });
  }
  const metadata = (tool.metadata as Record<string, unknown>) ?? {};
  const agentSchema = metadata.agent_params_json_schema as
    | { properties?: Record<string, unknown> }
    | undefined;
  if (agentSchema && agentSchema.properties) {
    Object.keys(agentSchema.properties).forEach((name) => {
      if (name) {
        collected.push(name);
      }
    });
  }
  const custom = metadata["execution_log_request_fields"];
  if (Array.isArray(custom)) {
    custom.forEach((entry) => {
      if (typeof entry === "string" && entry.trim()) {
        collected.push(entry.trim());
      }
    });
  }
  return uniqueNonEmpty(collected);
}

function inferResponseFieldOptions(tool: NetworkGraphTool): string[] {
  const hints: string[] = [];
  const metadata = (tool.metadata as Record<string, unknown>) ?? {};
  const provider = tool.provider_type ?? "";

  if (provider === "dialogflow:cx") {
    hints.push(
      "summary.message",
      "result.summary.message",
      "result.summary.intent",
      "result.summary.intent_confidence",
      "result.summary.parameters"
    );
  }

  const httpMeta = metadata.http as { response?: Record<string, unknown> } | undefined;
  if (httpMeta) {
    const responseMeta = httpMeta.response;
    if (responseMeta) {
      const unwrap = responseMeta.unwrap as string | undefined;
      if (typeof unwrap === "string" && unwrap.trim()) {
        hints.push(`result.${unwrap.trim()}`);
      }
      const keys = responseMeta.keys as unknown;
      if (Array.isArray(keys)) {
        keys.forEach((key) => {
          if (typeof key === "string" && key.trim()) {
            hints.push(`result.${key.trim()}`);
          }
        });
      }
    }
  }

  const custom = metadata["execution_log_response_fields"];
  if (Array.isArray(custom)) {
    custom.forEach((entry) => {
      if (typeof entry === "string" && entry.trim()) {
        hints.push(entry.trim());
      }
    });
  }

  if (hints.length === 0) {
    hints.push("result");
  }

  return uniqueNonEmpty(hints);
}

function uniqueNonEmpty(values: string[]): string[] {
  const seen = new Set<string>();
  values.forEach((value) => {
    const trimmed = value.trim();
    if (trimmed) {
      seen.add(trimmed);
    }
  });
  return Array.from(seen);
}
