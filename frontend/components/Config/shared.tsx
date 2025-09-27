"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  testTool,
  updateAgent,
  updateTool,
  duplicateAgent,
  duplicateTool,
  type AgentUpdatePayload,
  type ToolTestPayload,
  type ToolUpdatePayload
} from "@/lib/api/config";
import type { AgentSummary, ToolSummary, ToolTestResponse } from "@/lib/api/types";

type ApiError = Error & { status?: number; body?: unknown };

export function extractApiErrorMessage(error: unknown): string {
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

export function parseJsonObject(text: string, label: string): ParseResult {
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

export function parseJsonObjectOptional(
  text: string,
  label: string
): { ok: true; value?: Record<string, unknown> } | { ok: false; message: string } {
  if (!text.trim()) {
    return { ok: true, value: undefined };
  }
  const result = parseJsonObject(text, label);
  if (!result.ok) {
    return result;
  }
  return { ok: true, value: result.value };
}

export function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return `/* failed to render JSON: ${message} */`;
  }
}

export function LoadingState({ label }: { label: string }) {
  return <div className="text-sm text-foreground/60">Loading {label}…</div>;
}

export function ErrorState({ error }: { error: Error }) {
  return <div className="text-sm text-danger">{error.message}</div>;
}

export function AgentCard({ agent }: { agent: AgentSummary }) {
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [displayName, setDisplayName] = useState(agent.display_name ?? "");
  const [description, setDescription] = useState(agent.description ?? "");
  const [allowRespond, setAllowRespond] = useState(agent.allow_respond);
  const [isDefault, setIsDefault] = useState(agent.is_default);
  const [promptTemplate, setPromptTemplate] = useState(agent.prompt_template ?? "");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isCloning, setIsCloning] = useState(false);
  const [cloneKey, setCloneKey] = useState(`${agent.key}_copy`);
  const [cloneDisplayName, setCloneDisplayName] = useState(agent.display_name ?? "");
  const [cloneDescription, setCloneDescription] = useState(agent.description ?? "");
  const [cloneAllowRespond, setCloneAllowRespond] = useState(agent.allow_respond);
  const [cloneIsDefault, setCloneIsDefault] = useState(false);
  const [clonePromptTemplate, setClonePromptTemplate] = useState(agent.prompt_template ?? "");
  const [cloneError, setCloneError] = useState<string | null>(null);
  const [cloneToast, setCloneToast] = useState<string | null>(null);

  useEffect(() => {
    setDisplayName(agent.display_name ?? "");
    setDescription(agent.description ?? "");
    setAllowRespond(agent.allow_respond);
    setIsDefault(agent.is_default);
    setPromptTemplate(agent.prompt_template ?? "");
    setCloneKey(`${agent.key}_copy`);
    setCloneDisplayName(agent.display_name ?? "");
    setCloneDescription(agent.description ?? "");
    setCloneAllowRespond(agent.allow_respond);
    setCloneIsDefault(false);
    setClonePromptTemplate(agent.prompt_template ?? "");
    setCloneError(null);
    setCloneToast(null);
    setIsCloning(false);
  }, [
    agent.key,
    agent.display_name,
    agent.description,
    agent.allow_respond,
    agent.id,
    agent.is_default,
    agent.prompt_template
  ]);

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

  const cloneMutation = useMutation({
    mutationFn: (payload: {
      key: string;
      display_name?: string | null;
      description?: string | null;
      allow_respond: boolean;
      is_default: boolean;
      prompt_template?: string | null;
    }) =>
      duplicateAgent({
        networkId: agent.network_id,
        source: agent,
        key: payload.key,
        display_name: payload.display_name,
        description: payload.description,
        allow_respond: payload.allow_respond,
        is_default: payload.is_default,
        prompt_template: payload.prompt_template
      }),
    onSuccess: (data) => {
      setCloneError(null);
      setCloneToast(`Cloned agent to '${data.key}'`);
      setIsCloning(false);
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      queryClient.invalidateQueries({ queryKey: ["networks"] });
    },
    onError: (err) => {
      setCloneToast(null);
      setCloneError(extractApiErrorMessage(err));
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

  const toggleClone = () => {
    if (cloneMutation.isPending) {
      return;
    }
    if (isCloning) {
      setIsCloning(false);
      setCloneError(null);
      return;
    }
    setCloneToast(null);
    setCloneError(null);
    setCloneKey(`${agent.key}_copy`);
    setCloneDisplayName(agent.display_name ?? "");
    setCloneDescription(agent.description ?? "");
    setCloneAllowRespond(agent.allow_respond);
    setCloneIsDefault(false);
    setClonePromptTemplate(agent.prompt_template ?? "");
    setIsCloning(true);
  };

  const handleCloneSave = () => {
    setCloneError(null);
    setCloneToast(null);
    const trimmedKey = cloneKey.trim();
    if (!trimmedKey) {
      setCloneError("New agent key is required");
      return;
    }
    if (trimmedKey.toLowerCase() === agent.key.toLowerCase()) {
      setCloneError("Choose a different key for the clone");
      return;
    }
    if (cloneIsDefault && !cloneAllowRespond) {
      setCloneError("Default agents must allow RESPOND");
      return;
    }
    cloneMutation.mutate({
      key: trimmedKey,
      display_name: cloneDisplayName.trim() ? cloneDisplayName.trim() : null,
      description: cloneDescription.trim() ? cloneDescription.trim() : null,
      allow_respond: cloneAllowRespond,
      is_default: cloneIsDefault,
      prompt_template: clonePromptTemplate.trim() ? clonePromptTemplate : null
    });
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
            <>
              <button
                type="button"
                className="rounded border border-white/10 px-3 py-1 text-sm text-foreground/70 hover:border-white/30 disabled:opacity-60"
                onClick={toggleClone}
                disabled={cloneMutation.isPending}
              >
                {cloneMutation.isPending ? "Cloning…" : isCloning ? "Close clone" : "Clone"}
              </button>
              <button
                type="button"
                className="rounded border border-white/10 px-3 py-1 text-sm text-foreground/70 hover:border-white/30"
                onClick={() => setIsEditing(true)}
                disabled={cloneMutation.isPending}
              >
                Edit
              </button>
            </>
          )}
        </div>
      </header>

      {isCloning ? (
        <section className="mt-4 space-y-3 rounded border border-dashed border-white/10 bg-background/20 p-4">
          <h4 className="text-xs uppercase tracking-wide text-foreground/60">Clone agent</h4>
          <p className="text-xs text-foreground/60">Copy tools and routes from this agent into a new key.</p>
          <label className="block text-xs font-medium text-foreground/70">
            New key
            <input
              className="mt-1 w-full rounded border border-white/10 bg-background/40 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              value={cloneKey}
              onChange={(event) => setCloneKey(event.target.value)}
              disabled={cloneMutation.isPending}
              placeholder={`${agent.key}_copy`}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            Display name (optional)
            <input
              className="mt-1 w-full rounded border border-white/10 bg-background/40 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              value={cloneDisplayName}
              onChange={(event) => setCloneDisplayName(event.target.value)}
              disabled={cloneMutation.isPending}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            Description (optional)
            <textarea
              className="mt-1 w-full rounded border border-white/10 bg-background/40 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              rows={2}
              value={cloneDescription}
              onChange={(event) => setCloneDescription(event.target.value)}
              disabled={cloneMutation.isPending}
            />
          </label>
          <div className="flex flex-wrap gap-4 text-xs text-foreground/70">
            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={cloneAllowRespond}
                onChange={(event) => setCloneAllowRespond(event.target.checked)}
                disabled={cloneMutation.isPending}
              />
              Allow RESPOND
            </label>
            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={cloneIsDefault}
                onChange={(event) => setCloneIsDefault(event.target.checked)}
                disabled={cloneMutation.isPending}
              />
              Default agent
            </label>
          </div>
          <label className="block text-xs font-medium text-foreground/70">
            Prompt template (optional)
            <textarea
              className="mt-1 w-full rounded border border-white/10 bg-background/40 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              rows={4}
              value={clonePromptTemplate}
              onChange={(event) => setClonePromptTemplate(event.target.value)}
              disabled={cloneMutation.isPending}
            />
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
              onClick={handleCloneSave}
              disabled={cloneMutation.isPending}
            >
              {cloneMutation.isPending ? "Cloning…" : "Create clone"}
            </button>
            <button
              type="button"
              className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
              onClick={toggleClone}
              disabled={cloneMutation.isPending}
            >
              Cancel
            </button>
          </div>
          {cloneError ? <p className="text-xs text-danger">{cloneError}</p> : null}
        </section>
      ) : null}

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
                Runtime automatically appends context, constraints, tool definitions, and routes after this template.
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
      {cloneToast ? <p className="mt-2 text-xs text-emerald-400">{cloneToast}</p> : null}
    </article>
  );
}

export function ToolCard({ tool }: { tool: ToolSummary }) {
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [displayName, setDisplayName] = useState(tool.display_name ?? "");
  const [description, setDescription] = useState(tool.description ?? "");
  const [providerType, setProviderType] = useState(tool.provider_type ?? "");
  const [secretRef, setSecretRef] = useState(tool.secret_ref ?? "");
  const [paramsSchemaText, setParamsSchemaText] = useState(prettyJson(tool.params_schema));
  const [additionalDataText, setAdditionalDataText] = useState(prettyJson(tool.additional_data));
  const [editError, setEditError] = useState<string | null>(null);

  const [isCloning, setIsCloning] = useState(false);
  const [cloneKey, setCloneKey] = useState(`${tool.key}_copy`);
  const [cloneDisplayName, setCloneDisplayName] = useState(tool.display_name ?? "");
  const [cloneDescription, setCloneDescription] = useState(tool.description ?? "");
  const [cloneError, setCloneError] = useState<string | null>(null);
  const [cloneToast, setCloneToast] = useState<string | null>(null);

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
    setCloneKey(`${tool.key}_copy`);
    setCloneDisplayName(tool.display_name ?? "");
    setCloneDescription(tool.description ?? "");
    setCloneError(null);
    setCloneToast(null);
    setIsCloning(false);
  }, [tool.additional_data, tool.description, tool.display_name, tool.id, tool.key, tool.params_schema, tool.provider_type, tool.secret_ref]);

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

  const cloneMutation = useMutation({
    mutationFn: (payload: { key: string; display_name?: string | null; description?: string | null }) =>
      duplicateTool({
        source: tool,
        key: payload.key,
        display_name: payload.display_name ?? undefined,
        description: payload.description ?? undefined
      }),
    onSuccess: (data) => {
      setCloneError(null);
      setCloneToast(`Cloned tool to '${data.key}'`);
      setIsCloning(false);
      queryClient.invalidateQueries({ queryKey: ["tools"] });
    },
    onError: (err) => {
      setCloneToast(null);
      setCloneError(extractApiErrorMessage(err));
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
    const payload: ToolUpdatePayload = {
      display_name: displayName,
      description,
      provider_type: providerType,
      params_schema: paramsResult.value,
      secret_ref: secretRef,
      additional_data: metadataResult.value
    };
    mutation.mutate(payload);
  };

  const handleTest = () => {
    const paramsResult = parseJsonObject(testParamsText, "Invoke params");
    if (!paramsResult.ok) {
      setTestError(paramsResult.message);
      return;
    }
    const systemParamsResult = parseJsonObject(testSystemParamsText, "System params");
    if (!systemParamsResult.ok) {
      setTestError(systemParamsResult.message);
      return;
    }
    const additionalResult = parseJsonObjectOptional(testAdditionalDataText, "Additional data override");
    if (!additionalResult.ok) {
      setTestError(additionalResult.message);
      return;
    }
    setTestError(null);
    const payload: ToolTestPayload = {
      params: paramsResult.value,
      system_params: systemParamsResult.value,
      additional_data_override: additionalResult.value
    };
    testMutation.mutate(payload);
  };

  const toggleCloneTool = () => {
    if (cloneMutation.isPending) {
      return;
    }
    if (isCloning) {
      setIsCloning(false);
      setCloneError(null);
      return;
    }
    setCloneError(null);
    setCloneToast(null);
    setCloneKey(`${tool.key}_copy`);
    setCloneDisplayName(tool.display_name ?? "");
    setCloneDescription(tool.description ?? "");
    setIsCloning(true);
  };

  const handleCloneTool = () => {
    setCloneError(null);
    setCloneToast(null);
    const trimmedKey = cloneKey.trim();
    if (!trimmedKey) {
      setCloneError("New tool key is required");
      return;
    }
    if (trimmedKey.toLowerCase() === tool.key.toLowerCase()) {
      setCloneError("Choose a different key for the clone");
      return;
    }
    cloneMutation.mutate({
      key: trimmedKey,
      display_name: cloneDisplayName.trim() ? cloneDisplayName.trim() : null,
      description: cloneDescription.trim() ? cloneDescription.trim() : null
    });
  };

  return (
    <article className="rounded border border-white/10 bg-background/30 p-4">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-foreground">{displayName.trim() ? displayName : tool.key}</h3>
          <p className="text-xs font-mono text-foreground/40">{tool.key}</p>
          {tool.provider_type ? (
            <p className="mt-1 text-xs text-foreground/60">{tool.provider_type}</p>
          ) : null}
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
            <>
              <button
                type="button"
                className="rounded border border-white/10 px-3 py-1 text-sm text-foreground/70 hover:border-white/30 disabled:opacity-60"
                onClick={toggleCloneTool}
                disabled={cloneMutation.isPending}
              >
                {cloneMutation.isPending ? "Cloning…" : isCloning ? "Close clone" : "Clone"}
              </button>
              <button
                type="button"
                className="rounded border border-white/10 px-3 py-1 text-sm text-foreground/70 hover:border-white/30"
                onClick={() => setIsEditing(true)}
                disabled={cloneMutation.isPending}
              >
                Edit
              </button>
            </>
          )}
        </div>
      </header>

      {isCloning ? (
        <section className="mt-4 space-y-3 rounded border border-dashed border-white/10 bg-background/20 p-4">
          <h4 className="text-xs uppercase tracking-wide text-foreground/60">Clone tool</h4>
          <p className="text-xs text-foreground/60">Copies params and additional data from this tool. Provide a new key.</p>
          <label className="block text-xs font-medium text-foreground/70">
            New key
            <input
              className="mt-1 w-full rounded border border-white/10 bg-background/40 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              value={cloneKey}
              onChange={(event) => setCloneKey(event.target.value)}
              disabled={cloneMutation.isPending}
              placeholder={`${tool.key}_copy`}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            Display name (optional)
            <input
              className="mt-1 w-full rounded border border-white/10 bg-background/40 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              value={cloneDisplayName}
              onChange={(event) => setCloneDisplayName(event.target.value)}
              disabled={cloneMutation.isPending}
            />
          </label>
          <label className="block text-xs font-medium text-foreground/70">
            Description (optional)
            <textarea
              className="mt-1 w-full rounded border border-white/10 bg-background/40 px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              rows={2}
              value={cloneDescription}
              onChange={(event) => setCloneDescription(event.target.value)}
              disabled={cloneMutation.isPending}
            />
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
              onClick={handleCloneTool}
              disabled={cloneMutation.isPending}
            >
              {cloneMutation.isPending ? "Cloning…" : "Create clone"}
            </button>
            <button
              type="button"
              className="rounded border border-white/10 px-3 py-1 text-xs text-foreground/70 hover:border-white/30 disabled:opacity-60"
              onClick={toggleCloneTool}
              disabled={cloneMutation.isPending}
            >
              Cancel
            </button>
          </div>
          {cloneError ? <p className="text-xs text-danger">{cloneError}</p> : null}
        </section>
      ) : null}

      <section className="mt-4 space-y-4">
        {isEditing ? (
          <div className="space-y-4">
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Display name</label>
              <input
                className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Description</label>
              <textarea
                className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                rows={3}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Provider type</label>
                <input
                  className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                  value={providerType}
                  onChange={(event) => setProviderType(event.target.value)}
                />
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Secret ref</label>
                <input
                  className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                  value={secretRef}
                  onChange={(event) => setSecretRef(event.target.value)}
                />
              </div>
            </div>
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Params schema</label>
              <textarea
                className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                rows={6}
                value={paramsSchemaText}
                onChange={(event) => setParamsSchemaText(event.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Additional data</label>
              <textarea
                className="mt-1 w-full rounded border border-white/10 bg-background/60 px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                rows={6}
                value={additionalDataText}
                onChange={(event) => setAdditionalDataText(event.target.value)}
              />
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-foreground/60">{description?.trim() ? description : "No description."}</p>
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <h4 className="text-xs uppercase tracking-wide text-foreground/50">Secret ref</h4>
                <p className="mt-1 text-xs text-foreground/70">{secretRef || "—"}</p>
              </div>
              <div>
                <h4 className="text-xs uppercase tracking-wide text-foreground/50">Provider</h4>
                <p className="mt-1 text-xs text-foreground/70">{providerType || "—"}</p>
              </div>
            </div>
            <details className="rounded border border-white/10 bg-background/40 p-3">
              <summary className="text-xs font-semibold uppercase tracking-wide text-foreground/60">Params schema</summary>
              <pre className="mt-2 whitespace-pre-wrap text-xs text-foreground/70">{paramsSchemaText}</pre>
            </details>
            <details className="rounded border border-white/10 bg-background/40 p-3">
              <summary className="text-xs font-semibold uppercase tracking-wide text-foreground/60">Additional data</summary>
              <pre className="mt-2 whitespace-pre-wrap text-xs text-foreground/70">{additionalDataText}</pre>
            </details>
          </div>
        )}

        <div className="rounded border border-white/10 bg-background/20 p-3">
          <h4 className="text-xs uppercase tracking-wide text-foreground/50">Test connection</h4>
          <p className="mt-1 text-xs text-foreground/60">
            Submit a payload to verify connectivity. Uses the same control-plane endpoint as <code className="rounded bg-background/60 px-1">config/tools/:id/test_connection</code>.
          </p>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <div className="space-y-2">
              <label className="text-[11px] uppercase tracking-wide text-foreground/50">Invoke params</label>
              <textarea
                className="h-32 w-full rounded border border-white/10 bg-background/60 px-2 py-2 text-xs text-foreground outline-none focus:border-primary"
                value={testParamsText}
                onChange={(event) => setTestParamsText(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label className="text-[11px] uppercase tracking-wide text-foreground/50">System params</label>
              <textarea
                className="h-32 w-full rounded border border-white/10 bg-background/60 px-2 py-2 text-xs text-foreground outline-none focus:border-primary"
                value={testSystemParamsText}
                onChange={(event) => setTestSystemParamsText(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label className="text-[11px] uppercase tracking-wide text-foreground/50">Additional data override</label>
              <textarea
                className="h-32 w-full rounded border border-white/10 bg-background/60 px-2 py-2 text-xs text-foreground outline-none focus:border-primary"
                value={testAdditionalDataText}
                onChange={(event) => setTestAdditionalDataText(event.target.value)}
              />
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              className="rounded bg-primary/80 px-3 py-1 text-sm text-background hover:bg-primary disabled:opacity-60"
              onClick={handleTest}
              disabled={testMutation.isPending}
            >
              {testMutation.isPending ? "Testing…" : "Test tool"}
            </button>
            {testError ? <span className="text-xs text-danger">{testError}</span> : null}
          </div>
          {testResult ? (
            <div className="mt-3 rounded border border-emerald-500/40 bg-emerald-500/10 p-3 text-xs text-emerald-200">
              <p className="font-semibold">Test result</p>
              <pre className="mt-2 whitespace-pre-wrap text-[11px] text-emerald-100">
                {JSON.stringify(testResult, null, 2)}
              </pre>
            </div>
          ) : null}
        </div>

        {tool.source_tool_id ? (
          <p className="text-xs text-foreground/50">
            Source tool ID: {tool.source_tool_id}. Manage lineage via the CLI or <Link href="/config">Config</Link> workspace.
          </p>
        ) : null}
      </section>

      {editError ? <p className="mt-3 text-sm text-danger">{editError}</p> : null}
      {cloneToast ? <p className="mt-2 text-xs text-emerald-400">{cloneToast}</p> : null}
    </article>
  );
}
