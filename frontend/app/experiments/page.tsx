"use client";

import Link from "next/link";
import clsx from "clsx";
import { useCallback, useEffect, useMemo, useState, type MouseEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import {
  AgentCard,
  ErrorState,
  ToolCard,
  parseJsonObject,
  parseJsonObjectOptional
} from "@/components/Config/shared";
import { TraceHeader } from "@/components/TraceHeader/TraceHeader";
import { RunPlayback } from "@/components/TraceTimeline/RunPlayback";
import {
  fetchAgents,
  fetchNetworks,
  fetchNetworkGraph,
  fetchSystemParamDefaults,
  fetchTools
} from "@/lib/api/config";
import {
  fetchExperiments,
  fetchExperimentDetail,
  fetchExperimentRuns,
  startExperiment,
  uploadExperimentFile
} from "@/lib/api/experiments";
import type {
  AgentSummary,
  ExperimentDetail,
  ExperimentQueueItem,
  ExperimentRunHistoryEntry,
  ExperimentRunField,
  ExperimentSummary,
  ExperimentUploadResponse,
  NetworkSummary,
  ToolSummary
} from "@/lib/api/types";
import {
  SYSTEM_PARAM_OVERRIDES,
  deriveSystemParamMetadata,
  shallowEqualRecord,
  type SystemParamField,
  type ToolParamGroup
} from "@/lib/systemParams";
import { getRunSnapshot } from "@/lib/api/runs";

const DEFAULT_SCHEMA_HINT = {
  required: ["iterations"],
  optional: [
    "objective",
    "correct_behavior",
    "input_alias",
    "issue_description",
    "true_solution_description",
    "stopping_conditions",
    "correct_answer",
    "label"
  ],
  system_params_prefix: "system_params.*"
};

function generateExperimentId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return Math.random().toString(16).slice(2);
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch (err) {
    return value;
  }
}

function deriveStatus(summary: ExperimentSummary) {
  if (summary.in_progress > 0) return "Running";
  if (summary.queued > 0) return "Queued";
  if (summary.completed > 0 && summary.failed === 0) return "Completed";
  if (summary.completed > 0 && summary.failed > 0) return "Completed with failures";
  if (summary.failed > 0 && summary.completed === 0) return "Error - Not Completed";
  return "Pending";
}


type QueueItem = ExperimentQueueItem;

function normalizeString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}

function findNestedString(source: unknown, key: string): string | null {
  if (!source || typeof source !== "object") return null;
  const seen = new Set<object>();
  const stack: object[] = [source as object];

  while (stack.length) {
    const current = stack.pop();
    if (!current || seen.has(current)) continue;
    seen.add(current);

    for (const [entryKey, entryValue] of Object.entries(current)) {
      if (entryKey === key) {
        const normalized = normalizeString(entryValue);
        if (normalized) return normalized;
      }
      if (entryValue && typeof entryValue === "object") {
        stack.push(entryValue as object);
      }
    }
  }

  return null;
}

function extractVerdict(item: QueueItem): string | null {
  const direct = normalizeString(item.verdict);
  if (direct) return direct;

  const result = item.result;
  if (!result) return null;

  const resultDirect = normalizeString((result as { verdict?: unknown }).verdict);
  if (resultDirect) return resultDirect;

  return findNestedString(result, "verdict");
}

function extractAnswer(item: QueueItem): string | null {
  const directItem = normalizeString(item.answer);
  if (directItem) return directItem;

  const result = item.result;
  if (!result) return null;

  const direct = normalizeString((result as { answer?: unknown }).answer);
  if (direct) return direct;

  const actionDetails = result.action_details as Record<string, any> | undefined;
  if (actionDetails) {
    const payload = actionDetails.payload as Record<string, any> | undefined;
    if (payload) {
      const responsePayload = payload.response_payload as Record<string, any> | undefined;
      if (responsePayload) {
        const answer = normalizeString(responsePayload.answer);
        if (answer) return answer;
      }
    }
  }

  return findNestedString(result, "answer");
}

function formatVerdictLabel(value: string): string {
  const cleaned = value.replace(/_/g, " ").trim();
  if (!cleaned) return value;

  return cleaned
    .split(/\s+/)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}


export default function ExperimentsPage() {
  const [selectedNetworkId, setSelectedNetworkId] = useState<number | null>(null);
  const [experimentDesc, setExperimentDesc] = useState<string>("");
  const [experimentId, setExperimentId] = useState<string>(generateExperimentId);
  const [maxSteps, setMaxSteps] = useState<string>("");
  const [sharedSystemParams, setSharedSystemParams] = useState<Record<string, string>>({});
  const [extraSharedParamsText, setExtraSharedParamsText] = useState<string>("");
  const [manualRunInput, setManualRunInput] = useState<string>("Can a user have more than one account | Correct solution: A user can only have a maximum of one account");
  const [manualIterations, setManualIterations] = useState<string>("1");
  const [manualCorrectAnswer, setManualCorrectAnswer] = useState<string>("");
  const [manualLabel, setManualLabel] = useState<string>("");
  const [manualIssueDescription, setManualIssueDescription] = useState<string>("");
  const [manualTrueSolutionDescription, setManualTrueSolutionDescription] = useState<string>("");
  const [manualStoppingConditions, setManualStoppingConditions] = useState<string>("");
  const [manualSystemParamsText, setManualSystemParamsText] = useState<string>("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<ExperimentUploadResponse | null>(null);
  const [formMessage, setFormMessage] = useState<{ type: "error" | "success"; text: string } | null>(null);
  const [selectedExperimentId, setSelectedExperimentId] = useState<string | null>(null);
  const [runHistoryModal, setRunHistoryModal] = useState<{ experimentId: string; description: string | null } | null>(null);

  const {
    data: networks,
    isLoading: networksLoading,
    error: networksError
  } = useQuery({
    queryKey: ["networks"],
    queryFn: fetchNetworks,
    staleTime: 60_000
  });

  const {
    data: agents,
    isLoading: agentsLoading,
    error: agentsError
  } = useQuery({
    queryKey: ["agents"],
    queryFn: fetchAgents,
    staleTime: 60_000
  });

  const {
    data: tools,
    isLoading: toolsLoading,
    error: toolsError
  } = useQuery({
    queryKey: ["tools"],
    queryFn: fetchTools,
    staleTime: 60_000
  });

  const { data: systemDefaults } = useQuery({
    queryKey: ["system-param-defaults"],
    queryFn: fetchSystemParamDefaults,
    staleTime: 5 * 60_000
  });

  const selectedNetwork: NetworkSummary | null = useMemo(() => {
    if (!networks || selectedNetworkId == null) return null;
    return networks.find((net) => net.id === selectedNetworkId) ?? null;
  }, [networks, selectedNetworkId]);

  const {
    data: networkGraph,
    isFetching: networkGraphLoading,
    error: networkGraphError
  } = useQuery({
    queryKey: ["network", selectedNetwork?.id],
    queryFn: () => fetchNetworkGraph(selectedNetwork!.id),
    enabled: Boolean(selectedNetwork?.id),
    staleTime: 60_000
  });

  const { fields: systemParamFields, groups: toolParamGroups } = useMemo(
    () => deriveSystemParamMetadata(networkGraph),
    [networkGraph]
  );

  useEffect(() => {
    setSharedSystemParams((previous) => {
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

  const networkAgents = useMemo(() => {
    if (!selectedNetwork) return [] as AgentSummary[];
    return (agents ?? []).filter((agent) => agent.network_id === selectedNetwork.id);
  }, [agents, selectedNetwork]);

  const networkTools = useMemo(() => {
    if (!networkGraph?.tools) return [] as ToolSummary[];
    const idIndex = new Map<number, ToolSummary>();
    const keyIndex = new Map<string, ToolSummary>();
    (tools ?? []).forEach((tool) => {
      idIndex.set(tool.id, tool);
      keyIndex.set(tool.key.toLowerCase(), tool);
    });
    const seen = new Set<number>();
    const collected: ToolSummary[] = [];
    for (const tool of networkGraph.tools) {
      if (!tool?.key) continue;
      const summary =
        (tool.source_tool_id != null ? idIndex.get(tool.source_tool_id) : undefined) ??
        keyIndex.get(tool.key.toLowerCase());
      if (summary && !seen.has(summary.id)) {
        seen.add(summary.id);
        collected.push(summary);
      }
    }
    return collected;
  }, [networkGraph, tools]);

  const {
    data: experiments,
    isLoading: experimentsLoading,
    error: experimentsError,
    refetch: refetchExperiments
  } = useQuery({
    queryKey: ["experiments"],
    queryFn: fetchExperiments,
    refetchInterval: 15_000,
    staleTime: 5_000
  });

  const {
    data: experimentDetail,
    isFetching: detailFetching
  } = useQuery({
    queryKey: ["experiment-detail", selectedExperimentId],
    queryFn: () => fetchExperimentDetail(selectedExperimentId!),
    enabled: Boolean(selectedExperimentId),
    refetchInterval: (detail: ExperimentDetail | undefined) => {
      const queue = detail?.queue;
      if (!queue) return false;
      return queue.queued > 0 || queue.in_progress > 0 ? 5_000 : false;
    }
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadExperimentFile(file),
    onSuccess: (result) => {
      setUploadResult(result);
      setFormMessage(null);
    },
    onError: (error) => {
      setFormMessage({
        type: "error",
        text: (error as Error & { body?: { detail?: string } }).body?.detail ?? (error as Error).message
      });
    }
  });

  const launchMutation = useMutation({
    mutationFn: async () => {
      if (!selectedNetwork) {
        throw new Error("Select a network before launching an experiment.");
      }

      const trimmedExperimentId = experimentId.trim() || generateExperimentId();
      const trimmedDesc = experimentDesc.trim() || null;
      const trimmedMaxSteps = maxSteps.trim();
      let maxStepsValue: number | undefined;
      if (trimmedMaxSteps) {
        const parsed = Number.parseInt(trimmedMaxSteps, 10);
        if (!Number.isFinite(parsed) || parsed <= 0) {
          throw new Error("Max orchestrator steps must be a positive integer.");
        }
        maxStepsValue = parsed;
      }

      const structuredShared = Object.fromEntries(
        Object.entries(sharedSystemParams)
          .map(([key, value]) => [key, typeof value === "string" ? value.trim() : value])
          .filter(([, value]) => value !== undefined && value !== null && String(value).trim().length > 0)
      );

      let extraShared: Record<string, unknown> = {};
      if (extraSharedParamsText.trim()) {
        const parsed = parseJsonObject(extraSharedParamsText, "Additional shared system params");
        if (!parsed.ok) {
          throw new Error(parsed.message);
        }
        extraShared = parsed.value;
      }

      const sharedParams = { ...extraShared, ...structuredShared };

      let items = uploadResult?.items ?? [];
      const uploadHasErrors = Boolean(uploadResult?.errors && uploadResult.errors.length > 0);
      if (!items.length || uploadHasErrors) {
        const rawIterations = manualIterations.trim();
        const parsedIterations = Number.parseInt(rawIterations || "0", 10);
        if (!Number.isFinite(parsedIterations) || parsedIterations <= 0) {
          throw new Error("Iterations must be a positive integer.");
        }

        const manualParamsResult = parseJsonObjectOptional(manualSystemParamsText, "Manual system params");
        if (!manualParamsResult.ok) {
          throw new Error(manualParamsResult.message);
        }
        const manualParams = manualParamsResult.value ?? {};

        const metadata: Record<string, unknown> = {};
        if (manualIssueDescription.trim()) metadata.issue_description = manualIssueDescription.trim();
        if (manualTrueSolutionDescription.trim()) metadata.true_solution_description = manualTrueSolutionDescription.trim();
        if (manualStoppingConditions.trim()) metadata.stopping_conditions = manualStoppingConditions.trim();

        const manualItem = {
          run_input: manualRunInput.trim() || "start conversation",
          iterations: parsedIterations,
          correct_answer: manualCorrectAnswer.trim() ? manualCorrectAnswer.trim() : null,
          system_params: manualParams,
          metadata: Object.keys(metadata).length ? metadata : null,
          label: manualLabel.trim() ? manualLabel.trim() : null
        } satisfies ExperimentUploadResponse["items"][number];

        items = [manualItem];
      }

      if (!items.length) {
        throw new Error("No iterations to queue.");
      }

      return startExperiment({
        experiment_id: trimmedExperimentId,
        experiment_desc: trimmedDesc,
        network: selectedNetwork.name,
        agent_key: null,
        version: null,
        model: null,
        debug: false,
        shared_system_params: sharedParams,
        items,
        max_steps: maxStepsValue ?? null
      });
    },
    onSuccess: (response) => {
      setFormMessage({
        type: "success",
        text: `Experiment ${response.experiment_id} queued with ${response.total_runs} runs.`
      });
      setExperimentId(generateExperimentId());
      setSelectedExperimentId(response.experiment_id);
      refetchExperiments();
    },
    onError: (error) => {
      const message =
        (error as Error & { body?: { detail?: string } }).body?.detail ?? (error as Error).message;
      setFormMessage({ type: "error", text: message });
    }
  });

  const schemaHint = uploadResult?.schema_hint ?? DEFAULT_SCHEMA_HINT;
  const disableLaunch = launchMutation.isPending || !selectedNetwork;

  const handleValidate = () => {
    if (!selectedFile) {
      setFormMessage({ type: "error", text: "Select a CSV or JSONL file to validate." });
      return;
    }
    setFormMessage(null);
    uploadMutation.mutate(selectedFile);
  };

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      <div className="w-full max-w-xl border-r border-white/10 bg-surface/60 backdrop-blur">
        <div className="h-full overflow-y-auto p-6">
          <h1 className="text-xl font-semibold">Batch Experiments</h1>
          <p className="mt-2 text-sm text-foreground/70">
            Select a network to inspect its agents and tools, then queue runs by uploading a dataset or configuring a manual item.
          </p>

          <div className="mt-6 space-y-6">
            <fieldset className="space-y-2">
              <label className="block text-sm font-medium text-foreground">Network</label>
              <select
                className="w-full rounded-md border border-white/10 bg-background/40 px-3 py-2 text-sm"
                value={selectedNetworkId ?? ""}
                onChange={(event) => {
                  const next = event.target.value ? Number(event.target.value) : null;
                  setSelectedNetworkId(Number.isNaN(next) ? null : next);
                }}
              >
                <option value="">Select network…</option>
                {(networks ?? []).map((network) => (
                  <option key={network.id} value={network.id}>
                    {network.name}
                  </option>
                ))}
              </select>
              {networksLoading ? <p className="text-xs text-foreground/60">Loading networks…</p> : null}
              {networksError ? <p className="text-xs text-red-400">Unable to load networks.</p> : null}
            </fieldset>

            <fieldset className="space-y-2">
              <label className="block text-sm font-medium text-foreground">Experiment description</label>
              <textarea
                rows={2}
                value={experimentDesc}
                onChange={(event) => setExperimentDesc(event.target.value)}
                className="w-full rounded-md border border-white/10 bg-background/40 px-3 py-2 text-sm"
                placeholder="Regression sweep for multi-account policy"
              />
            </fieldset>

            <fieldset className="space-y-2">
              <label className="block text-sm font-medium text-foreground">Experiment ID</label>
              <input
                type="text"
                value={experimentId}
                onChange={(event) => setExperimentId(event.target.value)}
                className="w-full rounded-md border border-white/10 bg-background/40 px-3 py-2 text-sm"
              />
              <p className="text-xs text-foreground/60">Auto-generated if left blank.</p>
            </fieldset>

            <fieldset className="space-y-2">
              <label className="block text-sm font-medium text-foreground">Max orchestrator steps (optional)</label>
              <input
                type="number"
                min={1}
                value={maxSteps}
                onChange={(event) => setMaxSteps(event.target.value)}
                className="w-full rounded-md border border-white/10 bg-background/40 px-3 py-2 text-sm"
                placeholder="10"
              />
            </fieldset>

            <fieldset className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-foreground">Shared system params</label>
                <p className="mt-1 text-xs text-foreground/60">
                  Values apply to every queued iteration. Fields are inferred from the tools equipped to the network's default agent.
                </p>
              </div>
              <SystemParamInputs
                fields={systemParamFields}
                values={sharedSystemParams}
                onChange={(name, value) =>
                  setSharedSystemParams((previous) => ({
                    ...previous,
                    [name]: value
                  }))
                }
              />
              {toolParamGroups.length ? <ToolParamSummary groups={toolParamGroups} /> : null}
            </fieldset>

            <fieldset className="space-y-2">
              <label className="block text-sm font-medium text-foreground">Additional shared params (JSON)</label>
              <textarea
                rows={3}
                value={extraSharedParamsText}
                onChange={(event) => setExtraSharedParamsText(event.target.value)}
                className="w-full rounded-md border border-white/10 bg-background/40 px-3 py-2 text-sm"
                placeholder='{ "username": "CSTESTINR", "customer_verified": true }'
              />
              <p className="text-xs text-foreground/60">Optional JSON object merged with the structured fields above.</p>
            </fieldset>

            <div className="space-y-3 rounded-md border border-white/10 bg-background/40 p-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-foreground">Manual experiment item</h2>
                <span className="rounded-full bg-white/10 px-2 py-1 text-xs text-foreground/70">Used when no file is uploaded</span>
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-foreground">Run Input</label>
                <textarea
                  rows={3}
                  value={manualRunInput}
                  onChange={(event) => setManualRunInput(event.target.value)}
                  className="w-full rounded-md border border-white/10 bg-background/60 px-3 py-2 text-sm"
                  placeholder="You are a customer of Dafabet…"
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="block text-sm font-medium text-foreground">Iterations</label>
                  <input
                    type="number"
                    min={1}
                    value={manualIterations}
                    onChange={(event) => setManualIterations(event.target.value)}
                    className="w-full rounded-md border border-white/10 bg-background/60 px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground">Correct answer (optional)</label>
                  <input
                    type="text"
                    value={manualCorrectAnswer}
                    onChange={(event) => setManualCorrectAnswer(event.target.value)}
                    className="w-full rounded-md border border-white/10 bg-background/60 px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground">Label (optional)</label>
                  <input
                    type="text"
                    value={manualLabel}
                    onChange={(event) => setManualLabel(event.target.value)}
                    className="w-full rounded-md border border-white/10 bg-background/60 px-3 py-2 text-sm"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-foreground">Issue description (optional)</label>
                <textarea
                  rows={2}
                  value={manualIssueDescription}
                  onChange={(event) => setManualIssueDescription(event.target.value)}
                  className="w-full rounded-md border border-white/10 bg-background/60 px-3 py-2 text-sm"
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-foreground">True solution description (optional)</label>
                <textarea
                  rows={2}
                  value={manualTrueSolutionDescription}
                  onChange={(event) => setManualTrueSolutionDescription(event.target.value)}
                  className="w-full rounded-md border border-white/10 bg-background/60 px-3 py-2 text-sm"
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-foreground">Stopping conditions (optional)</label>
                <textarea
                  rows={2}
                  value={manualStoppingConditions}
                  onChange={(event) => setManualStoppingConditions(event.target.value)}
                  className="w-full rounded-md border border-white/10 bg-background/60 px-3 py-2 text-sm"
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-foreground">Manual system params (JSON, optional)</label>
                <textarea
                  rows={3}
                  value={manualSystemParamsText}
                  onChange={(event) => setManualSystemParamsText(event.target.value)}
                  className="w-full rounded-md border border-white/10 bg-background/60 px-3 py-2 text-sm"
                  placeholder="{}"
                />
              </div>
            </div>

            <fieldset className="space-y-2">
              <label className="block text-sm font-medium text-foreground">Experiment file (optional)</label>
              <input
                type="file"
                accept=".csv,.jsonl"
                onChange={(event) => {
                  const file = event.target.files?.[0] ?? null;
                  setSelectedFile(file);
                  setUploadResult(null);
                  setFormMessage(null);
                }}
                className="w-full text-sm text-foreground"
              />
              <p className="text-xs text-foreground/60">
                Columns supported: required <span className="font-medium">{schemaHint.required.join(", ")}</span>; optional {schemaHint.optional.join(", ")}. Use
                <code className="ml-1 rounded bg-background/60 px-1">{schemaHint.system_params_prefix}</code> for tool parameters (values should be JSON literals).
              </p>
            </fieldset>

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={handleValidate}
                disabled={uploadMutation.isPending || !selectedFile}
              >
                {uploadMutation.isPending ? "Validating…" : "Validate file"}
              </button>
              <button
                type="button"
                className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => launchMutation.mutate()}
                disabled={disableLaunch}
              >
                {launchMutation.isPending ? "Launching…" : "Launch experiment"}
              </button>
            </div>

            {formMessage ? (
              <div
                className={`rounded-md border px-3 py-2 text-sm ${
                  formMessage.type === "error" ? "border-red-500/60 bg-red-500/10 text-red-200" : "border-emerald-500/60 bg-emerald-500/10 text-emerald-200"
                }`}
              >
                {formMessage.text}
              </div>
            ) : null}

            {uploadResult ? (
              <div className="space-y-3 rounded-md border border-white/10 bg-background/40 p-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-foreground">Validation summary</h2>
                  <span className="rounded-full bg-white/10 px-2 py-1 text-xs text-foreground/80">
                    {uploadResult.count} item{uploadResult.count === 1 ? "" : "s"}
                  </span>
                </div>
                {uploadResult.errors && uploadResult.errors.length > 0 ? (
                  <div className="rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
                    <p className="font-medium">Errors</p>
                    <ul className="mt-1 space-y-1">
                      {uploadResult.errors.map((error) => (
                        <li key={`error-${error.row}`}>Row {error.row}: {error.error}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {uploadResult.warnings && uploadResult.warnings.length > 0 ? (
                  <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
                    <p className="font-medium">Warnings</p>
                    <ul className="mt-1 space-y-1">
                      {uploadResult.warnings.map((warning, idx) => (
                        <li key={`warn-${warning.row}-${idx}`}>Row {warning.row}: {warning.message}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {uploadResult.preview && uploadResult.preview.length > 0 ? (
                  <div className="space-y-2 text-xs text-foreground/80">
                    <p className="font-medium">Preview (first {uploadResult.preview.length} rows)</p>
                    <pre className="max-h-48 overflow-auto rounded bg-black/40 p-3">
                      {JSON.stringify(uploadResult.preview, null, 2)}
                    </pre>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-white/10 bg-surface/40">
          <div className="flex items-center justify-between px-6 py-4">
            <h2 className="text-lg font-semibold">Experiment history</h2>
            <button
              type="button"
              className="rounded-md border border-white/10 px-3 py-1 text-xs text-foreground/80 hover:border-white/30"
              onClick={() => refetchExperiments()}
            >
              Refresh
            </button>
          </div>
          <div className="max-h-64 overflow-y-auto px-6 pb-4">
            {experimentsLoading ? (
              <p className="text-sm text-foreground/60">Loading experiments…</p>
            ) : null}
            {experimentsError ? (
              <p className="text-sm text-red-400">Unable to load experiments.</p>
            ) : null}
            {!experimentsLoading && !experimentsError && (!experiments || experiments.length === 0) ? (
              <p className="text-sm text-foreground/60">No experiments queued yet.</p>
            ) : null}
            {experiments && experiments.length > 0 ? (
              <table className="w-full table-fixed text-left text-sm">
                <thead>
                  <tr className="text-xs uppercase tracking-wide text-foreground/60">
                    <th className="w-44 pb-2">Experiment</th>
                    <th className="pb-2">Description</th>
                    <th className="w-24 pb-2">Status</th>
                    <th className="w-24 pb-2 text-right">Runs</th>
                    <th className="w-32 pb-2 text-right">Completed</th>
                    <th className="w-32 pb-2 text-right">Error - Not Completed</th>
                    <th className="w-32 pb-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {experiments.map((summary) => {
                    const status = deriveStatus(summary);
                    const isActive = summary.experiment_id === selectedExperimentId;
                    return (
                      <tr
                        key={summary.experiment_id}
                        className={`cursor-pointer transition-colors ${
                          isActive ? "bg-white/5" : "hover:bg-white/5"
                        }`}
                        onClick={() => setSelectedExperimentId(summary.experiment_id)}
                      >
                        <td className="truncate pr-4 py-2 text-xs font-medium text-foreground">
                          {summary.experiment_id}
                        </td>
                        <td className="truncate pr-4 py-2 text-xs text-foreground/80">
                          {summary.description || "—"}
                        </td>
                        <td className="pr-4 py-2 text-xs text-foreground/70">{status}</td>
                        <td className="pr-4 py-2 text-right text-xs text-foreground/70">{summary.total_runs}</td>
                        <td className="pr-4 py-2 text-right text-xs text-emerald-300">{summary.completed}</td>
                        <td className="py-2 pr-4 text-right text-xs text-red-300">{summary.failed}</td>
                        <td className="py-2 text-right">
                          <button
                            type="button"
                            className="rounded-md border border-white/10 px-2 py-1 text-[11px] uppercase tracking-wide text-foreground/80 hover:border-white/30"
                            onClick={(event) => {
                              event.stopPropagation();
                              setRunHistoryModal({
                                experimentId: summary.experiment_id,
                                description: summary.description || null
                              });
                            }}
                          >
                            View runs
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : null}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="space-y-8">
            <NetworkDetailsPanel
              network={selectedNetwork}
              graphError={networkGraphError as Error | undefined}
              graphLoading={networkGraphLoading}
              agents={networkAgents}
              agentsLoading={agentsLoading}
              agentsError={agentsError as Error | undefined}
              tools={networkTools}
              toolsLoading={toolsLoading}
              toolsError={toolsError as Error | undefined}
            />

            {selectedExperimentId == null ? (
              <p className="text-sm text-foreground/60">Select an experiment to view progress.</p>
            ) : detailFetching && !experimentDetail ? (
              <p className="text-sm text-foreground/60">Loading experiment details…</p>
            ) : experimentDetail ? (
              <ExperimentDetailPanel detail={experimentDetail} />
            ) : (
              <p className="text-sm text-red-400">Unable to load experiment details.</p>
            )}
          </div>
        </div>
      </div>
      {runHistoryModal ? (
        <ExperimentRunsModal
          experimentId={runHistoryModal.experimentId}
          experimentDescription={runHistoryModal.description}
          onClose={() => setRunHistoryModal(null)}
        />
      ) : null}
    </div>
  );
}

function SystemParamInputs({
  fields,
  values,
  onChange
}: {
  fields: SystemParamField[];
  values: Record<string, string>;
  onChange: (name: string, value: string) => void;
}) {
  if (!fields.length) {
    return <p className="text-sm text-foreground/60">No shared system params detected for the selected network.</p>;
  }

  return (
    <div className="space-y-3">
      {fields.map((field) => {
        const override = SYSTEM_PARAM_OVERRIDES[field.name] ?? {};
        const value = values[field.name] ?? "";
        const labelText = override.label ?? field.name;
        const appliesTo = field.tools.length ? `Applies to: ${field.tools.join(", ")}` : null;
        const requiredBadge = field.required ? <span className="ml-1 text-xs text-red-300">*</span> : null;

        return (
          <div key={field.name} className="space-y-1">
            <label className="block text-sm font-medium text-foreground">
              {labelText}
              {requiredBadge}
            </label>
            {override.inputType === "textarea" ? (
              <textarea
                rows={override.rows ?? 3}
                value={value}
                onChange={(event) => onChange(field.name, event.target.value)}
                className="w-full rounded-md border border-white/10 bg-background/60 px-3 py-2 text-sm"
              />
            ) : (
              <input
                type="text"
                value={value}
                onChange={(event) => onChange(field.name, event.target.value)}
                className="w-full rounded-md border border-white/10 bg-background/60 px-3 py-2 text-sm"
              />
            )}
            {override.help ? <p className="text-xs text-foreground/60">{override.help}</p> : null}
            {appliesTo ? <p className="text-[11px] text-foreground/50">{appliesTo}</p> : null}
          </div>
        );
      })}
    </div>
  );
}

function ToolParamSummary({ groups }: { groups: ToolParamGroup[] }) {
  if (!groups.length) {
    return null;
  }

  return (
    <div className="rounded-md border border-white/10 bg-background/40 p-3 text-xs text-foreground/70">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-foreground/50">Tool parameter coverage</h3>
      <ul className="mt-2 space-y-2">
        {groups.map((group) => (
          <li key={group.toolKey}>
            <p className="font-medium text-foreground">{group.displayName || group.toolKey}</p>
            <p className="text-foreground/60">{group.description || "No description provided."}</p>
            {group.systemParams.length ? (
              <p className="text-foreground/50">
                Fields: {group.systemParams.map((param) => `${param.name}${param.required ? "*" : ""}`).join(", ")}
              </p>
            ) : (
              <p className="text-foreground/50">No system params required.</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function NetworkDetailsPanel({
  network,
  graphLoading,
  graphError,
  agents,
  agentsLoading,
  agentsError,
  tools,
  toolsLoading,
  toolsError
}: {
  network: NetworkSummary | null;
  graphLoading: boolean;
  graphError: Error | undefined;
  agents: AgentSummary[];
  agentsLoading: boolean;
  agentsError: Error | undefined;
  tools: ToolSummary[];
  toolsLoading: boolean;
  toolsError: Error | undefined;
}) {
  if (!network) {
    return <p className="text-sm text-foreground/60">Select a network to review its configuration.</p>;
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-foreground">{network.name}</h2>
        <p className="text-sm text-foreground/70">{network.description || "No description provided."}</p>
        <p className="text-xs text-foreground/50">Active snapshot: {network.current_version_id ?? "unpublished"}</p>
        {graphLoading ? <p className="mt-1 text-xs text-foreground/60">Loading graph metadata…</p> : null}
        {graphError ? <p className="mt-1 text-xs text-red-400">Unable to load graph metadata.</p> : null}
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-foreground">Agents</h3>
          {agentsLoading ? <span className="text-xs text-foreground/60">Loading…</span> : null}
        </div>
        {agentsError ? <ErrorState error={agentsError} /> : null}
        {!agentsLoading && !agentsError && agents.length === 0 ? (
          <p className="text-sm text-foreground/60">No agents found for this network.</p>
        ) : null}
        <div className="space-y-4">
          {agents.map((agent) => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-foreground">Tools</h3>
          {toolsLoading ? <span className="text-xs text-foreground/60">Loading…</span> : null}
        </div>
        {toolsError ? <ErrorState error={toolsError} /> : null}
        {!toolsLoading && !toolsError && tools.length === 0 ? (
          <p className="text-sm text-foreground/60">No tools associated with this network.</p>
        ) : null}
        <div className="space-y-4">
          {tools.map((tool) => (
            <ToolCard key={tool.id} tool={tool} />
          ))}
        </div>
      </div>
    </section>
  );
}

function ExperimentDetailPanel({ detail }: { detail: ExperimentDetail }) {
  const [expandedRow, setExpandedRow] = useState<number | null>(null);
  const experimentId = detail.experiment.experiment_id;
  const queueItems = detail.queue?.items ?? [];
  const hasQueueItems = queueItems.length > 0;

  const verdictSummary = useMemo(() => {
    if (!hasQueueItems) {
      return [] as { verdict: string; label: string; count: number }[];
    }

    const counts: Record<string, number> = {};
    for (const item of queueItems) {
      const verdictValue = extractVerdict(item);
      if (!verdictValue) continue;
      counts[verdictValue] = (counts[verdictValue] ?? 0) + 1;
    }

    return Object.entries(counts)
      .map(([verdict, count]) => ({
        verdict,
        label: formatVerdictLabel(verdict),
        count
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [hasQueueItems, queueItems]);

  const handleExport = useCallback(() => {
    if (!hasQueueItems) {
      return;
    }

    if (typeof window === "undefined") {
      return;
    }

    const headers = ["Row", "Iteration", "Status", "Verdict", "Answer", "Trace", "Error"];
    const toCsvCell = (value: string): string => `"${value.replace(/"/g, '""')}"`;

    const rows = queueItems.map((item) => {
      const verdictValue = extractVerdict(item) ?? "";
      const answerValue = extractAnswer(item) ?? "";
      const traceId = normalizeString(item.result?.trace_id) ?? "";
      const errorValue = item.error ?? "";

      return [
        String(item.item_index + 1),
        String(item.iteration),
        String(item.status ?? ""),
        verdictValue,
        answerValue,
        traceId,
        errorValue
      ];
    });

    const csvContent = [headers, ...rows]
      .map((row) => row.map((cell) => toCsvCell(cell)).join(","))
      .join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `experiment-${experimentId}-queue.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [experimentId, hasQueueItems, queueItems]);

  const toggleRow = (id: number) => {
    setExpandedRow(expandedRow === id ? null : id);
  };

  return (
    <section className="space-y-6">
      <div className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold text-foreground">Experiment {detail.experiment.experiment_id}</h3>
            <p className="mt-1 text-sm text-foreground/70">{detail.experiment.description || "No description provided."}</p>
          </div>
          <button
            type="button"
            className="inline-flex items-center rounded-md border border-white/10 px-3 py-1 text-xs font-medium text-foreground hover:border-white/30 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={handleExport}
            disabled={!hasQueueItems}
          >
            Export
          </button>
        </div>
        {detail.queue ? (
          <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-foreground/70 sm:grid-cols-3">
            <div>
              <p className="font-medium text-foreground/80">Queued</p>
              <p>{detail.queue.queued ?? 0}</p>
            </div>
            <div>
              <p className="font-medium text-foreground/80">In progress</p>
              <p>{detail.queue.in_progress ?? 0}</p>
            </div>
            <div>
              <p className="font-medium text-foreground/80">Completed</p>
              <p className="text-emerald-300">{detail.queue.completed ?? 0}</p>
            </div>
            <div>
              <p className="font-medium text-foreground/80">Error - Not Completed</p>
              <p className="text-red-300">{detail.queue.failed ?? 0}</p>
            </div>
            <div>
              <p className="font-medium text-foreground/80">Started</p>
              <p>{formatDate(detail.queue.started_at)}</p>
            </div>
            <div>
              <p className="font-medium text-foreground/80">Completed at</p>
              <p>{formatDate(detail.queue.completed_at)}</p>
            </div>
          </div>
        ) : (
          <p className="mt-3 text-xs text-foreground/60">Queue metrics are unavailable for this experiment.</p>
        )}
        {verdictSummary.length > 0 ? (
          <div className="mt-4 rounded-md border border-white/10 bg-background/40 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-foreground/60">Verdict totals</p>
            <div className="mt-2 grid grid-cols-2 gap-3 text-sm text-foreground/80 sm:grid-cols-3">
              {verdictSummary.map(({ verdict, label, count }) => (
                <div key={verdict} className="rounded bg-white/5 p-2">
                  <p className="text-xs uppercase tracking-wide text-foreground/60">{label}</p>
                  <p className="text-base font-semibold text-foreground">{count}</p>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <div>
        <h4 className="text-sm font-semibold text-foreground">Queue</h4>
        {!detail.queue ? (
          <p className="text-sm text-foreground/60">Queue details are unavailable.</p>
        ) : detail.queue.items.length === 0 ? (
          <p className="text-sm text-foreground/60">No queue items recorded.</p>
        ) : (
          <div className="mt-2 max-h-96 overflow-y-auto rounded-md border border-white/10">
            <table className="w-full table-fixed text-left text-xs">
              <thead className="bg-white/5 text-foreground/60">
                <tr>
                  <th className="w-12 px-3 py-2">Row</th>
                  <th className="w-12 px-3 py-2">Iter</th>
                  <th className="w-24 px-3 py-2">Status</th>
                  <th className="w-24 px-3 py-2">Verdict</th>
                  <th className="px-3 py-2">Answer</th>
                  <th className="px-3 py-2">Trace</th>
                  <th className="px-3 py-2">Error</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {detail.queue.items.map((item) => {
                  const verdict = extractVerdict(item);
                  const answer = extractAnswer(item);
                  const traceId = normalizeString(item.result?.trace_id);
                  const isExpanded = expandedRow === item.id;
                  return (
                    <>
                      <tr key={item.id} className="text-foreground/80 cursor-pointer hover:bg-white/5" onClick={() => toggleRow(item.id)}>
                        <td className="px-3 py-2">{item.item_index + 1}</td>
                        <td className="px-3 py-2">{item.iteration}</td>
                        <td className="px-3 py-2 text-foreground/70">{item.status}</td>
                        <td className="px-3 py-2">
                          {verdict ? (
                            <span
                              className={clsx("rounded-full px-2 py-0.5 text-xs font-medium", {
                                "bg-green-500/20 text-green-300": verdict === "pass",
                                "bg-red-500/20 text-red-300": verdict === "fail",
                                "bg-yellow-500/20 text-yellow-300": verdict !== "pass" && verdict !== "fail"
                              })}
                            >
                              {verdict}
                            </span>
                          ) : (
                            <span className="text-foreground/50">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-foreground/70 whitespace-pre-wrap break-words">
                          {answer ? answer : <span className="text-foreground/50">—</span>}
                        </td>
                        <td className="px-3 py-2">
                          {traceId ? (
                            <Link href={`/runs/${encodeURIComponent(traceId)}`} className="text-primary underline-offset-2 hover:underline">
                              {traceId.substring(0, 8)}...
                            </Link>
                          ) : (
                            <span className="text-foreground/50">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-red-300">
                          {item.error ? item.error : <span className="text-foreground/50">—</span>}
                        </td>
                      </tr>
                      {isExpanded && item.evaluation_notes && (
                        <tr>
                          <td colSpan={7} className="p-4 bg-background/50">
                            <div className="rounded-md bg-gray-800 p-3">
                              <p className="text-sm font-semibold text-foreground/80">Evaluation Notes:</p>
                              <p className="mt-1 text-xs text-foreground/70 whitespace-pre-wrap">{item.evaluation_notes}</p>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

function ExperimentRunsModal({
  experimentId,
  experimentDescription,
  onClose
}: {
  experimentId: string;
  experimentDescription: string | null;
  onClose: () => void;
}) {
  const { data, isFetching, error } = useQuery({
    queryKey: ["experiment-runs", experimentId],
    queryFn: () => fetchExperimentRuns(experimentId),
    enabled: Boolean(experimentId),
    staleTime: 30_000
  });

  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [activeTraceId, setActiveTraceId] = useState<string | null>(null);

  useEffect(() => {
    if (!data?.fields) {
      return;
    }
    setSelectedColumns((previous) => {
      if (previous.length) {
        return previous;
      }
      return data.fields.filter((field) => field.default).map((field) => field.key);
    });
  }, [data?.fields]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const toggleColumn = useCallback((key: string) => {
    setSelectedColumns((previous) => {
      if (previous.includes(key)) {
        return previous.filter((entry) => entry !== key);
      }
      return [...previous, key];
    });
  }, []);

  const selectedFields = useMemo(() => {
    if (!data?.fields) return [] as ExperimentRunField[];
    const index = new Map(data.fields.map((field) => [field.key, field] as const));
    return selectedColumns
      .map((key) => index.get(key))
      .filter((field): field is ExperimentRunField => Boolean(field));
  }, [data?.fields, selectedColumns]);

  const runs: ExperimentRunHistoryEntry[] = (data?.runs as ExperimentRunHistoryEntry[]) ?? [];

  const verdictSummary = useMemo(() => {
    if (!runs.length) {
      return [] as { verdict: string; label: string; count: number }[];
    }

    const counts: Record<string, number> = {};
    for (const run of runs) {
      const verdictValue = normalizeString(run.verdict);
      if (!verdictValue) continue;
      counts[verdictValue] = (counts[verdictValue] ?? 0) + 1;
    }

    return Object.entries(counts)
      .map(([verdict, count]) => ({
        verdict,
        label: formatVerdictLabel(verdict),
        count
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [runs]);

  const formatForCsv = (value: unknown): string => {
    if (value === null || value === undefined) {
      return "";
    }
    if (typeof value === "string") {
      return value;
    }
    if (typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
    try {
      return JSON.stringify(value);
    } catch (err) {
      return String(value);
    }
  };

  const exportCsv = useCallback(() => {
    if (!data || !selectedFields.length || !runs.length) {
      return;
    }
    const headers = ["Row", ...selectedFields.map((field) => field.label)];
    const rows = runs.map((run, index) => {
      const cells = selectedFields.map((field) => {
        const value = (run as ExperimentRunHistoryEntry)[field.key];
        return formatForCsv(value);
      });
      return [String(index + 1), ...cells];
    });

    const csvLines = [headers, ...rows]
      .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
      .join("\n");

    const blob = new Blob([csvLines], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `experiment-${experimentId}-runs.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [data, experimentId, runs, selectedFields]);

  const renderValue = (fieldKey: string, value: unknown) => {
    if (fieldKey === "trace_id" && typeof value === "string" && value) {
      return (
        <a
          href="#"
          className="text-primary underline-offset-2 hover:underline"
          onClick={(event) => {
            event.preventDefault();
            setActiveTraceId(value);
          }}
        >
          {value.substring(0, 8)}...
        </a>
      );
    }

    if (fieldKey === "answer" && typeof value === "string") {
      return <span className="text-foreground/80 whitespace-pre-wrap">{value}</span>;
    }

    if (fieldKey === "duration_ms" && typeof value === "number") {
      return <span className="text-foreground/80">{value.toLocaleString()} ms</span>;
    }

    if (fieldKey === "item_index" && typeof value === "number") {
      return <span className="text-foreground/80">{value + 1}</span>;
    }

    if (fieldKey === "error" && typeof value === "string") {
      return <span className="text-red-300 whitespace-pre-wrap">{value}</span>;
    }

    if (value === null || value === undefined || value === "") {
      return <span className="text-foreground/50">—</span>;
    }

    if (typeof value === "string") {
      return <span className="text-foreground/80 whitespace-pre-wrap break-words">{value}</span>;
    }

    if (typeof value === "number" || typeof value === "boolean") {
      return <span className="text-foreground/80">{String(value)}</span>;
    }

    try {
      const serialized = JSON.stringify(value, null, 2);
      return (
        <div className="max-h-40 overflow-auto rounded-md bg-black/40 p-2 text-[11px] text-foreground/70">
          <pre className="whitespace-pre-wrap break-words">{serialized}</pre>
        </div>
      );
    } catch (err) {
      return <span className="text-foreground/80">{String(value)}</span>;
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-6"
      onClick={onClose}
    >
      <div
        className="w-full max-w-6xl overflow-hidden rounded-lg border border-white/10 bg-background/95 backdrop-blur"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-white/10 px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Run history for {experimentId}</h2>
            {experimentDescription ? (
              <p className="text-sm text-foreground/70">{experimentDescription}</p>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded-md border border-white/10 px-3 py-1 text-xs text-foreground/80 hover:border-white/30 disabled:opacity-50"
              onClick={exportCsv}
              disabled={!runs.length || !selectedFields.length}
            >
              Export CSV
            </button>
            <button
              type="button"
              className="rounded-md border border-white/10 px-3 py-1 text-xs text-foreground/80 hover:border-white/30"
              onClick={onClose}
            >
              Close
            </button>
          </div>
        </div>

        <div className="px-6 py-4 space-y-4">
          {error ? (
            <p className="text-sm text-red-400">Unable to load run history.</p>
          ) : null}
          {verdictSummary.length > 0 ? (
            <div className="rounded-md border border-white/10 bg-background/40 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-foreground/60">Verdict totals</p>
              <div className="mt-2 grid grid-cols-2 gap-3 text-sm text-foreground/80 sm:grid-cols-3">
                {verdictSummary.map(({ verdict, label, count }) => (
                  <div
                    key={verdict}
                    className={clsx("rounded p-2", {
                      "bg-green-500/20": verdict === "pass",
                      "bg-red-500/20": verdict === "fail",
                      "bg-yellow-500/20": verdict !== "pass" && verdict !== "fail"
                    })}
                  >
                    <p
                      className={clsx("text-xs uppercase tracking-wide", {
                        "text-green-300": verdict === "pass",
                        "text-red-300": verdict === "fail",
                        "text-yellow-300": verdict !== "pass" && verdict !== "fail"
                      })}
                    >
                      {label}
                    </p>
                    <p
                      className={clsx("text-base font-semibold", {
                        "text-green-100": verdict === "pass",
                        "text-red-100": verdict === "fail",
                        "text-yellow-100": verdict !== "pass" && verdict !== "fail"
                      })}
                    >
                      {count}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-foreground/60">Columns</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {(data?.fields ?? []).map((field) => {
                const selected = selectedColumns.includes(field.key);
                return (
                  <label
                    key={field.key}
                    className={clsx(
                      "flex items-center gap-2 rounded border px-2 py-1 text-xs",
                      selected
                        ? "border-primary/60 bg-primary/20 text-primary"
                        : "border-white/10 bg-background/60 text-foreground/70"
                    )}
                  >
                    <input
                      type="checkbox"
                      className="h-3 w-3 accent-primary"
                      checked={selected}
                      onChange={() => toggleColumn(field.key)}
                    />
                    {field.label}
                  </label>
                );
              })}
            </div>
          </div>

          {isFetching ? (
            <p className="text-sm text-foreground/60">Loading run entries…</p>
          ) : null}

          {!isFetching && !error && runs.length === 0 ? (
            <p className="text-sm text-foreground/60">No runs recorded for this experiment.</p>
          ) : null}

          {runs.length > 0 && selectedFields.length > 0 ? (
            <div className="max-h-[60vh] overflow-auto rounded-md border border-white/10">
              <table className="w-full table-fixed text-left text-xs">
                <thead className="bg-white/5 text-foreground/60">
                  <tr>
                    <th className="w-12 px-3 py-2">Row</th>
                    {selectedFields.map((field) => (
                      <th key={field.key} className="px-3 py-2">
                        {field.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 text-foreground/80">
                  {runs.map((run, index) => (
                    <tr key={`${run.run_id}-${index}`} className="align-top">
                      <td className="px-3 py-2">{index + 1}</td>
                      {selectedFields.map((field) => {
                        const value = (run as ExperimentRunHistoryEntry)[field.key];
                        return (
                          <td key={field.key} className="px-3 py-2">
                            {renderValue(field.key, value)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </div>
      {activeTraceId ? (
        <RunTraceModal
          traceId={activeTraceId}
          onClose={() => setActiveTraceId(null)}
        />
      ) : null}
    </div>
  );
}

function RunTraceModal({ traceId, onClose }: { traceId: string; onClose: () => void }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["run-snapshot", traceId],
    queryFn: () => getRunSnapshot(traceId),
    staleTime: 30_000,
  });

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const handleBackdropClick = (event: MouseEvent<HTMLDivElement>) => {
    event.stopPropagation();
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 p-6" onClick={handleBackdropClick}>
      <div
        className="relative flex h-[90vh] w-[95vw] max-w-6xl flex-col overflow-hidden rounded-lg border border-white/10 bg-background/98 backdrop-blur"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
          <div>
            <h3 className="text-lg font-semibold text-foreground">Trace {traceId}</h3>
            <p className="text-xs text-foreground/60">Interactive playback</p>
          </div>
          <button
            type="button"
            className="rounded-md border border-white/10 px-3 py-1 text-xs text-foreground/80 hover:border-white/30"
            onClick={onClose}
          >
            Close
          </button>
        </div>

        {isLoading ? (
          <div className="flex flex-1 items-center justify-center text-sm text-foreground/60">
            Loading trace…
          </div>
        ) : error ? (
          <div className="flex flex-1 items-center justify-center text-sm text-red-400">
            Unable to load trace.
          </div>
        ) : data ? (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <TraceHeader traceId={traceId} graphVersionId={(data.graphVersionId ?? data.metadata?.graph_version_key ?? undefined) as string | undefined} />
            <RunPlayback
              traceId={traceId}
              initialSteps={data.steps}
              graphVersionId={(() => {
                const graphId = data.graphVersionId ?? data.metadata?.graph_version_key ?? null;
                return graphId != null ? String(graphId) : undefined;
              })()}
              networkName={(() => {
                const name = data.metadata?.network_name;
                if (name && name.trim().length) return name;
                const id = data.metadata?.network_id;
                return id != null ? String(id) : undefined;
              })()}
              variant="modal"
            />
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-foreground/60">
            Trace not found.
          </div>
        )}
      </div>
    </div>
  );
}
