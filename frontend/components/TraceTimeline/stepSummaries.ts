import type { RunEnvelope } from "@/lib/api/types";

export type TimelineStatus = "success" | "failure" | "unknown";

export interface AgentStepSummary {
  actorLabel: string;
  actionLabel: string;
  detailLabel?: string;
  reasonLabel?: string;
  status: TimelineStatus;
  duration?: number;
}

export interface ToolStepSummary {
  detailLabel: string;
  status: TimelineStatus;
  statusLabel?: string;
  actorLabel?: string;
  duration?: number;
  toolLabel: string;
}

export interface NonLogSummary {
  label: string;
  detail?: string;
}

export function summarizeAgentPayload(payload: Record<string, unknown> | undefined): AgentStepSummary {
  const agentKey = typeof payload?.agent_key === "string" ? payload.agent_key : "agent";
  const decisionFull = (payload?.decision_full ?? payload?.decision) as Record<string, unknown> | undefined;
  const action = typeof decisionFull?.action === "string" ? decisionFull.action : undefined;
  const upperAction = action?.toUpperCase() ?? "UNKNOWN";

  let actionLabel: string = upperAction;
  if (upperAction === "ROUTE_TO_AGENT") actionLabel = "ROUTE";
  else if (upperAction === "USE_TOOL") actionLabel = "TOOL";
  else if (upperAction === "RESPOND") actionLabel = "RESPOND";

  let detailLabel: string | undefined;
  if (upperAction === "ROUTE_TO_AGENT") {
    const details = decisionFull?.action_details as Record<string, unknown> | undefined;
    const target = typeof details?.target_agent_name === "string" ? details.target_agent_name : undefined;
    detailLabel = `Route Target: ${target ?? "unknown"}`;
  } else if (upperAction === "USE_TOOL") {
    const details = decisionFull?.action_details as Record<string, unknown> | undefined;
    const tool = typeof details?.tool_name === "string" ? details.tool_name : undefined;
    detailLabel = `Tool Name: ${tool ?? "unknown"}`;
  }

  const reasoning = typeof decisionFull?.action_reasoning === "string" ? decisionFull.action_reasoning : undefined;
  const hasError = typeof payload?.error === "string" && payload.error.length > 0;
  const parsedOk = Boolean(action);
  const status: TimelineStatus = !parsedOk || hasError ? "failure" : "success";
  const duration = typeof payload?.duration_ms === "number" ? payload.duration_ms : undefined;

  return {
    actorLabel: `Agent · ${agentKey}`,
    actionLabel,
    detailLabel,
    reasonLabel: reasoning,
    status,
    duration
  };
}

export function summarizeToolPayload(payload: Record<string, unknown> | undefined): ToolStepSummary {
  const toolKey = typeof payload?.tool_key === "string" ? payload.tool_key : "tool";
  const agentKey = typeof payload?.agent_key === "string" ? payload.agent_key : undefined;
  const statusRaw = typeof payload?.status === "string" ? payload.status.toLowerCase() : "";
  const successStatuses = new Set(["ok", "success", "completed"]);
  let status: TimelineStatus = "unknown";
  if (statusRaw) {
    status = successStatuses.has(statusRaw) ? "success" : "failure";
  }
  const duration = typeof payload?.duration_ms === "number" ? payload.duration_ms : undefined;
  const statusLabel = statusRaw ? `Status: ${payload?.status}` : undefined;

  return {
    detailLabel: `Tool Name: ${toolKey}`,
    status,
    statusLabel,
    actorLabel: agentKey ? `Agent · ${agentKey}` : undefined,
    duration,
    toolLabel: toolKey
  };
}

export function describeNonLogStep(step: RunEnvelope["step"]): NonLogSummary {
  switch (step.kind) {
    case "visit_node":
      return { label: `Visited ${step.nodeId}` };
    case "traverse_edge":
      return { label: `Traversed ${step.edgeKey}` };
    case "attach_evidence":
      return { label: `Attached evidence (${step.evidenceIds.length})` };
    case "vector_lookup":
      return { label: "Vector lookup", detail: `${step.hits.length} hits` };
    case "cypher":
      return { label: "Cypher query", detail: `${step.duration_ms} ms` };
    default:
      return { label: step.kind };
  }
}
