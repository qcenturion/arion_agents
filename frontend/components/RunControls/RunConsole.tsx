"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { fetchNetworkGraph, fetchNetworks, fetchSystemParamDefaults } from "@/lib/api/config";
import { fetchRecentRuns, getRunSnapshot, triggerRun } from "@/lib/api/runs";
import { usePlaybackStore } from "@/stores/usePlaybackStore";
import type {
  ExecutionLogEntry,
  NetworkSummary,
  RunEnvelope,
  RunMetadata,
  RunRequestPayload,
  RunResponsePayload,
  RunSnapshot
} from "@/lib/api/types";

interface SystemParamField {
  name: string;
  tools: string[];
  required: boolean;
}

interface RunHistoryOption {
  traceId: string;
  label: string;
  createdAt?: string | null;
}

export function RunConsole() {
  const [prompt, setPrompt] = useState("");
  const [selectedNetwork, setSelectedNetwork] = useState<NetworkSummary | null>(null);
  const [systemParams, setSystemParams] = useState<Record<string, string>>({});
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRunFinal, setSelectedRunFinal] = useState<Record<string, unknown> | null>(null);

  const setInitialSteps = usePlaybackStore((state) => state.setInitialSteps);
  const resetPlayback = usePlaybackStore((state) => state.reset);

  const {
    data: networks,
    isLoading: networksLoading,
    isError: networksError,
    error: networksErrorObj
  } = useQuery({
    queryKey: ["networks"],
    queryFn: fetchNetworks,
    staleTime: 60_000
  });

  const { data: systemDefaults } = useQuery({
    queryKey: ["system-param-defaults"],
    queryFn: fetchSystemParamDefaults,
    staleTime: 5 * 60_000
  });

  const {
    data: networkGraph
  } = useQuery({
    queryKey: ["network-graph", selectedNetwork?.id],
    queryFn: () => fetchNetworkGraph(selectedNetwork!.id),
    enabled: Boolean(selectedNetwork?.id),
    staleTime: 60_000
  });

  const {
    data: runs,
    isFetching: runsFetching,
    refetch: refetchRuns
  } = useQuery({
    queryKey: ["runs"],
    queryFn: fetchRecentRuns,
    staleTime: 30_000
  });

  const {
    data: activeRun,
    isFetching: activeRunFetching
  } = useQuery({
    queryKey: ["run", selectedRunId],
    queryFn: () => getRunSnapshot(selectedRunId!),
    enabled: Boolean(selectedRunId)
  });

  const systemParamFields = useMemo<SystemParamField[]>(
    () => extractSystemParamFields(networkGraph),
    [networkGraph]
  );

  const networksById = useMemo(() => {
    const map = new Map<number, NetworkSummary>();
    (networks ?? []).forEach((network) => {
      map.set(network.id, network);
    });
    return map;
  }, [networks]);

  const runOptions: RunHistoryOption[] = useMemo(() => {
    if (!runs) return [];
    return runs.map((run) => {
      const meta: RunMetadata | undefined = run.metadata;
      const createdAt = meta?.created_at ?? null;
      const networkName = meta?.network_id ? networksById.get(meta.network_id)?.name : undefined;
      const labelParts = [run.traceId];
      if (createdAt) {
        labelParts.push(new Date(createdAt).toLocaleString());
      }
      if (networkName) {
        labelParts.push(networkName);
      }
      return {
        traceId: run.traceId,
        label: labelParts.join(" · "),
        createdAt
      };
    });
  }, [runs, networksById]);

  useEffect(() => {
    if (!selectedRunId && runOptions.length) {
      setSelectedRunId(runOptions[0].traceId);
    }
  }, [runOptions, selectedRunId]);

  useEffect(() => {
    setSystemParams((previous) => {
      if (!systemParamFields.length) {
        return Object.keys(previous).length ? {} : previous;
      }
      const defaults = systemDefaults ?? {};
      const next: Record<string, string> = {};
      for (const field of systemParamFields) {
        const prior = previous[field.name];
        next[field.name] = prior ?? defaults[field.name] ?? "";
      }
      return shallowEqualRecord(previous, next) ? previous : next;
    });
  }, [systemParamFields, systemDefaults]);

  useEffect(() => {
    if (!activeRun) {
      return;
    }
    const steps = deriveStepsFromSnapshot(activeRun);
    setInitialSteps(steps);
    const finalPayload = (activeRun.metadata?.final ?? null) as Record<string, unknown> | null;
    setSelectedRunFinal(finalPayload);
  }, [activeRun, setInitialSteps]);

  const mutation = useMutation({
    mutationFn: (payload: RunRequestPayload) => triggerRun(payload),
    onSuccess: async (data: RunResponsePayload) => {
      const traceId = data.trace_id ?? generateLocalTraceId();
      const steps = deriveRunSteps(data, traceId);
      setInitialSteps(steps);
      setSelectedRunFinal(data.final ?? null);
      setSelectedRunId(traceId);
      await refetchRuns();
    }
  });

  const missingRequired = useMemo(
    () =>
      systemParamFields.some((field) => {
        if (!field.required) return false;
        const value = systemParams[field.name];
        return !value || !value.trim().length;
      }),
    [systemParamFields, systemParams]
  );

  const readyToRun = Boolean(
    prompt.trim().length && selectedNetwork && !missingRequired && !mutation.isPending
  );

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedNetwork) return;
    const cleanedSystem = Object.fromEntries(
      Object.entries(systemParams).filter(([, value]) => value != null && value !== "")
    );
    const payload: RunRequestPayload = {
      network: selectedNetwork.name,
      user_message: prompt.trim(),
      system_params: cleanedSystem
    };
    mutation.mutate(payload);
  };

  const handleReset = () => {
    resetPlayback();
    setPrompt("");
    setSystemParams({});
    setSelectedRunFinal(null);
    setSelectedRunId(null);
  };

  const networkOptionsList = useMemo(() => networks ?? [], [networks]);

  return (
    <form onSubmit={handleSubmit} className="flex flex-1 flex-col gap-6 overflow-y-auto bg-surface/70 p-6">
      <div>
        <h2 className="text-lg font-semibold text-foreground">Run Console</h2>
        <p className="mt-2 text-sm text-foreground/60">
          Choose a network snapshot, supply system configuration, and provide an operator prompt. Runs execute against the orchestrator API and hydrate the timeline on completion.
        </p>
      </div>

      <div className="space-y-2">
        <label htmlFor="network" className="text-xs uppercase tracking-wide text-foreground/50">
          Network
        </label>
        {networksLoading ? (
          <div className="text-sm text-foreground/60">Loading networks…</div>
        ) : networksError ? (
          <div className="text-sm text-danger">
            Failed to load networks: {(networksErrorObj as Error)?.message ?? "unknown error"}
          </div>
        ) : (
          <select
            id="network"
            name="network"
            className="w-full rounded border border-white/10 bg-background/30 px-3 py-2 text-sm text-foreground"
            value={selectedNetwork?.id ?? ""}
            onChange={(event) => {
              const id = Number(event.target.value);
              const match = networkOptionsList.find((net) => net.id === id) ?? null;
              setSelectedNetwork(match);
            }}
          >
            <option value="">Select network…</option>
            {networkOptionsList.map((network) => (
              <option key={network.id} value={network.id}>
                {network.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {systemParamFields.length ? (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase tracking-wide text-foreground/50">System parameters</span>
            <span className="text-[10px] uppercase tracking-wide text-foreground/40">Applied per tool</span>
          </div>
          <div className="space-y-3">
            {systemParamFields.map((field) => (
              <div key={field.name} className="space-y-1">
                <label className="flex flex-col text-xs font-medium uppercase tracking-wide text-foreground/50">
                  <span>
                    {field.name}
                    {field.required ? <span className="ml-1 text-danger">*</span> : null}
                  </span>
                  <span className="mt-1 text-[10px] normal-case text-foreground/40">
                    Tools: {field.tools.join(", ") || "runtime"}
                  </span>
                </label>
                <input
                  type="text"
                  value={systemParams[field.name] ?? ""}
                  onChange={(event) =>
                    setSystemParams((prev) => ({ ...prev, [field.name]: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-background/30 px-3 py-2 text-sm text-foreground focus:border-primary/60 focus:outline-none"
                  placeholder={systemDefaults?.[field.name] ?? ""}
                />
              </div>
            ))}
          </div>
          {missingRequired ? (
            <p className="text-xs text-warning/80">Fill all required fields before running.</p>
          ) : null}
        </div>
      ) : null}

      <div className="space-y-2">
        <label htmlFor="prompt" className="text-xs uppercase tracking-wide text-foreground/50">
          Operator prompt
        </label>
        <textarea
          id="prompt"
          name="prompt"
          className="h-32 w-full resize-y rounded border border-white/10 bg-background/30 px-3 py-2 text-sm text-foreground"
          placeholder="e.g. When is sunset in Paris?"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
        />
      </div>

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={!readyToRun}
          className="rounded bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors disabled:cursor-not-allowed disabled:bg-primary/30"
        >
          {mutation.isPending ? "Running…" : "Run"}
        </button>
        <button
          type="button"
          onClick={handleReset}
          className="rounded border border-white/10 px-4 py-2 text-sm text-foreground/70 hover:border-white/20"
        >
          Reset
        </button>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs uppercase tracking-wide text-foreground/50">
          <span>Run history</span>
          <button
            type="button"
            onClick={() => void refetchRuns()}
            className="rounded border border-white/10 px-2 py-1 text-[10px] text-foreground/60 hover:border-white/20"
          >
            Refresh
          </button>
        </div>
        {runsFetching && !runOptions.length ? (
          <div className="text-sm text-foreground/60">Loading runs…</div>
        ) : runOptions.length ? (
          <select
            className="w-full rounded border border-white/10 bg-background/30 px-3 py-2 text-sm text-foreground"
            value={selectedRunId ?? ""}
            onChange={(event) => setSelectedRunId(event.target.value || null)}
          >
            <option value="">Select run…</option>
            {runOptions.map((option) => (
              <option key={option.traceId} value={option.traceId}>
                {option.label}
              </option>
            ))}
          </select>
        ) : (
          <div className="text-sm text-foreground/60">No runs recorded yet.</div>
        )}
        {activeRunFetching ? (
          <div className="text-xs text-foreground/50">Loading selected run…</div>
        ) : null}
      </div>

      {selectedRunFinal ? (
        <div className="rounded border border-white/10 bg-background/20 p-3 text-xs text-foreground/80">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">Final response</h3>
            {selectedRunId ? (
              <Link href={`/runs/${selectedRunId}`} className="text-xs text-primary underline">
                Trace view
              </Link>
            ) : null}
          </div>
          <pre className="mt-2 whitespace-pre-wrap break-words font-mono text-xs">
            {JSON.stringify(selectedRunFinal, null, 2)}
          </pre>
        </div>
      ) : null}
    </form>
  );
}

function deriveRunSteps(data: RunResponsePayload, traceId: string): RunEnvelope[] {
  if (Array.isArray(data.step_events) && data.step_events.length) {
    return data.step_events.map((event, idx) => ({
      traceId,
      seq: typeof event.seq === "number" ? event.seq : idx,
      t: typeof event.t === "number" ? event.t : Date.now() + idx,
      step: event.step as RunEnvelope["step"]
    }));
  }
  return normalizeExecutionLog(data.execution_log ?? [], traceId);
}

function deriveStepsFromSnapshot(snapshot: RunSnapshot): RunEnvelope[] {
  if (snapshot.steps?.length) {
    return snapshot.steps.map((step, idx) => ({
      traceId: step.traceId ?? snapshot.traceId,
      seq: typeof step.seq === "number" ? step.seq : idx,
      t: typeof step.t === "number" ? step.t : Date.now() + idx,
      step: step.step
    }));
  }
  return [];
}

function normalizeExecutionLog(entries: ExecutionLogEntry[], traceId: string): RunEnvelope[] {
  return entries.map((entry, idx) => ({
    traceId,
    seq: idx,
    t: Date.now() + idx,
    step: {
      kind: "log_entry" as const,
      entryType: typeof entry.type === "string" ? entry.type : "log",
      payload: entry as Record<string, unknown>
    }
  }));
}

function extractSystemParamFields(graph: any): SystemParamField[] {
  if (!graph || !Array.isArray(graph?.agents) || !Array.isArray(graph?.tools)) {
    return [];
  }
  const defaultAgent = graph.agents.find((agent: any) => agent.is_default) ?? graph.agents[0];
  if (!defaultAgent || !Array.isArray(defaultAgent.equipped_tools)) {
    return [];
  }
  const toolIndex = new Map<string, any>();
  for (const tool of graph.tools) {
    if (tool?.key) {
      toolIndex.set(String(tool.key).toLowerCase(), tool);
    }
  }
  const accumulator = new Map<string, SystemParamField>();
  for (const rawKey of defaultAgent.equipped_tools) {
    const key = String(rawKey ?? "").toLowerCase();
    const tool = toolIndex.get(key);
    if (!tool) continue;
    const paramsSchema = tool.params_schema ?? {};
    Object.entries(paramsSchema).forEach(([paramName, schema]) => {
      const spec = (schema as Record<string, unknown>) ?? {};
      if ((spec.source ?? "agent") !== "system") {
        return;
      }
      const field = accumulator.get(paramName) ?? {
        name: paramName,
        tools: [],
        required: false
      };
      field.required = field.required || Boolean(spec.required);
      if (!field.tools.includes(tool.key)) {
        field.tools.push(tool.key);
      }
      accumulator.set(paramName, field);
    });
  }
  return Array.from(accumulator.values()).sort((a, b) => a.name.localeCompare(b.name));
}

function shallowEqualRecord(a: Record<string, string>, b: Record<string, string>): boolean {
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  if (aKeys.length !== bKeys.length) {
    return false;
  }
  return aKeys.every((key) => a[key] === b[key]);
}

function generateLocalTraceId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `run-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
