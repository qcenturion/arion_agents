"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Sigma from "sigma";
import Graph from "graphology";
import clsx from "clsx";
import type { RunEnvelope } from "@/lib/api/types";
import { usePlaybackStore } from "@/stores/usePlaybackStore";
import {
  describeNonLogStep,
  summarizeAgentPayload,
  summarizeToolPayload,
  type TimelineStatus
} from "@/components/TraceTimeline/stepSummaries";

type FlowNodeKind = "agent" | "tool" | "system";

interface FlowNodeMeta {
  id: string;
  seq: number;
  kind: FlowNodeKind;
  title: string;
  subtitle?: string;
  detail?: string;
  durationLabel?: string;
  status: TimelineStatus;
}

interface FlowEdgeMeta {
  id: string;
  source: string;
  target: string;
  kind: "sequential" | "retry";
  retryCount?: number;
}

interface FlowStructure {
  nodes: FlowNodeMeta[];
  edges: FlowEdgeMeta[];
}

interface RunFlowGraphProps {
  steps: RunEnvelope[];
  onExpand?: () => void;
  orientation?: "vertical" | "horizontal";
}

interface NodePosition {
  left: number;
  top: number;
}

interface RetryBadgePosition {
  id: string;
  left: number;
  top: number;
  retryCount: number;
}

interface GraphBounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

const NODE_WIDTH = 160;
const NODE_HEIGHT = 70;
const MINI_NODE_SIZE = 14;
const MINI_GAP = 18;
const CARD_PADDING_WIDTH = NODE_WIDTH;
const CARD_PADDING_HEIGHT = NODE_HEIGHT;

export function RunFlowGraph({ steps, onExpand, orientation = "vertical" }: RunFlowGraphProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);

  const seekTo = usePlaybackStore((state) => state.seekTo);
  const cursorSeq = usePlaybackStore((state) => state.cursorSeq);

  const structure = useMemo(() => buildFlowStructure(steps), [steps]);

  const [nodePositions, setNodePositions] = useState<Record<string, NodePosition>>({});
  const [retryBadges, setRetryBadges] = useState<RetryBadgePosition[]>([]);
  const [containerSize, setContainerSize] = useState<{ width: number; height: number }>({ width: 0, height: 0 });

  const alignOverlay = useCallback(
    (nodes: Record<string, NodePosition>, retryLabels: RetryBadgePosition[]) => {
      const container = containerRef.current;
      if (!container || !Object.keys(nodes).length) {
        setNodePositions(nodes);
        setRetryBadges(retryLabels);
        return;
      }

      const containerWidth = container.clientWidth;
      const containerHeight = container.clientHeight;
      setContainerSize({ width: containerWidth, height: containerHeight });

      const xs = Object.values(nodes).map((pos) => pos.left);
      const ys = Object.values(nodes).map((pos) => pos.top);
      const minLeft = Math.min(...xs);
      const maxLeft = Math.max(...xs);
      const minTop = Math.min(...ys);
      const maxTop = Math.max(...ys);

      const margin = 80;
      const availableWidth = Math.max(containerWidth - margin - CARD_PADDING_WIDTH, 1);
      const availableHeight = Math.max(containerHeight - margin - CARD_PADDING_HEIGHT, 1);
      const width = Math.max(maxLeft - minLeft, 1);
      const height = Math.max(maxTop - minTop, 1);
      const scale = Math.min(3, Math.min(availableWidth / width, availableHeight / height));
      const centerLeft = (minLeft + maxLeft) / 2;
      const centerTop = (minTop + maxTop) / 2;

      const adjustedNodes: Record<string, NodePosition> = {};
      Object.entries(nodes).forEach(([key, pos]) => {
        adjustedNodes[key] = {
          left: (pos.left - centerLeft) * scale + containerWidth / 2,
          top: (pos.top - centerTop) * scale + containerHeight / 2
        };
      });

      setNodePositions(adjustedNodes);
      setRetryBadges(
        retryLabels.map((badge) => ({
          ...badge,
          left: (badge.left - centerLeft) * scale + containerWidth / 2,
          top: (badge.top - centerTop) * scale + containerHeight / 2
        }))
      );
    },
    []
  );

  useEffect(() => {
    if (process.env.NODE_ENV !== "production") {
      console.debug("RunFlowGraph structure", {
        steps: steps.length,
        nodes: structure.nodes.length,
        edges: structure.edges.length
      });
    }
  }, [steps, structure, alignOverlay]);

  useEffect(() => {
    const host = canvasRef.current;
    if (!host) return () => undefined;

    if (!structure.nodes.length) {
      setNodePositions({});
      setRetryBadges([]);
      if (sigmaRef.current) {
        sigmaRef.current.kill();
        sigmaRef.current = null;
      }
      graphRef.current = null;
      return () => undefined;
    }

    let disposed = false;

    const graph = new Graph({ type: "directed", multi: true });

    const orderedNodes = structure.nodes.slice().sort((a, b) => a.seq - b.seq);
    const count = orderedNodes.length;
    const verticalGap = NODE_HEIGHT * 1.4;
    const totalGraphHeight = Math.max(count - 1, 1) * verticalGap;
    const minY = -totalGraphHeight / 2;
    const maxY = totalGraphHeight / 2;
    const minX = -NODE_WIDTH / 2;
    const maxX = NODE_WIDTH / 2;

    if (orientation === "horizontal") {
      const horizontalGap = NODE_WIDTH * 1.6;
      const totalWidth = Math.max(orderedNodes.length - 1, 1) * horizontalGap;
      const minX = -totalWidth / 2;
      const maxX = totalWidth / 2;
      const centerY = 0;

      orderedNodes.forEach((meta, index) => {
        const positionX = minX + index * horizontalGap;
        graph.addNode(meta.id, {
          ...meta,
          x: positionX,
          y: centerY,
          highlighted: false
        });
      });

      structure.edges.forEach((edge) => {
        if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) {
          return;
        }
        graph.addDirectedEdgeWithKey(edge.id, edge.source, edge.target, {
          kind: edge.kind,
          retryCount: edge.retryCount,
          size: edge.kind === "retry" ? 2.4 : 1.6,
          color: edge.kind === "retry" ? "#ef4444" : "#64748b",
          type: "arrow"
        });
      });

    const bounds: GraphBounds = { minX, maxX, minY: centerY - NODE_HEIGHT, maxY: centerY + NODE_HEIGHT };

    if (sigmaRef.current) {
      sigmaRef.current.kill();
      sigmaRef.current = null;
    }

    const renderer = initializeRenderer(graph, host, seekTo);
    applyCaptors(renderer);

    const updateOverlay = () => {
      if (disposed) return;
      const nodes: Record<string, NodePosition> = {};
      const retryLabels: RetryBadgePosition[] = [];
      graph.forEachNode((node: string) => {
        const attrs = graph.getNodeAttributes(node) as FlowNodeMeta & {
          x: number;
          y: number;
        };
        const viewport = renderer.graphToViewport({ x: attrs.x, y: attrs.y });
        nodes[node] = { left: viewport.x, top: viewport.y };
      });
      graph.forEachEdge((edge: string) => {
        const attrs = graph.getEdgeAttributes(edge) as FlowEdgeMeta;
        if (attrs.kind !== "retry" || typeof attrs.retryCount !== "number") {
          return;
        }
        const source = graph.source(edge);
        const target = graph.target(edge);
        const sourceAttrs = graph.getNodeAttributes(source) as { x: number; y: number };
        const targetAttrs = graph.getNodeAttributes(target) as { x: number; y: number };
        const sourceViewport = renderer.graphToViewport({ x: sourceAttrs.x, y: sourceAttrs.y });
        const targetViewport = renderer.graphToViewport({ x: targetAttrs.x, y: targetAttrs.y });
        retryLabels.push({
          id: edge,
          retryCount: attrs.retryCount,
          left: (sourceViewport.x + targetViewport.x) / 2,
          top: (sourceViewport.y + targetViewport.y) / 2 - 12
        });
      });
      alignOverlay(nodes, retryLabels);
    };

    renderer.on("afterRender", updateOverlay);

    fitCameraToBounds(renderer, bounds, host);
    renderer.refresh();
    updateOverlay();
    prepareCanvas(host);

    sigmaRef.current = renderer;
    graphRef.current = graph;

    return () => {
      disposed = true;
      if (sigmaRef.current) {
        sigmaRef.current.kill();
        sigmaRef.current = null;
      }
      graphRef.current = null;
    };
  }

    orderedNodes.forEach((meta, index) => {
      const positionY = maxY - index * verticalGap;
      graph.addNode(meta.id, {
        ...meta,
        x: 0,
        y: positionY,
        highlighted: false
      });
    });

    structure.edges.forEach((edge) => {
      if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) {
        return;
      }
      graph.addDirectedEdgeWithKey(edge.id, edge.source, edge.target, {
        kind: edge.kind,
        retryCount: edge.retryCount,
        size: edge.kind === "retry" ? 2.4 : 1.6,
        color: edge.kind === "retry" ? "#ef4444" : "#64748b",
        type: "arrow"
      });
    });

    if (sigmaRef.current) {
      sigmaRef.current.kill();
      sigmaRef.current = null;
    }

    const renderer = initializeRenderer(graph, host, seekTo);
    applyCaptors(renderer);

    const bounds: GraphBounds = { minX, maxX, minY, maxY };

    const updateOverlay = () => {
      if (disposed) return;
      const nodes: Record<string, NodePosition> = {};
      const retryLabels: RetryBadgePosition[] = [];
      graph.forEachNode((node: string) => {
        const attrs = graph.getNodeAttributes(node) as FlowNodeMeta & {
          x: number;
          y: number;
        };
        const viewport = renderer.graphToViewport({ x: attrs.x, y: attrs.y });
        nodes[node] = { left: viewport.x, top: viewport.y };
      });
      graph.forEachEdge((edge: string) => {
        const attrs = graph.getEdgeAttributes(edge) as FlowEdgeMeta;
        if (attrs.kind !== "retry" || typeof attrs.retryCount !== "number") {
          return;
        }
        const source = graph.source(edge);
        const target = graph.target(edge);
        const sourceAttrs = graph.getNodeAttributes(source) as { x: number; y: number };
        const targetAttrs = graph.getNodeAttributes(target) as { x: number; y: number };
        const sourceViewport = renderer.graphToViewport({ x: sourceAttrs.x, y: sourceAttrs.y });
        const targetViewport = renderer.graphToViewport({ x: targetAttrs.x, y: targetAttrs.y });
        retryLabels.push({
          id: edge,
          retryCount: attrs.retryCount,
          left: (sourceViewport.x + targetViewport.x) / 2,
          top: (sourceViewport.y + targetViewport.y) / 2 - 12
        });
      });
      alignOverlay(nodes, retryLabels);
      if (process.env.NODE_ENV !== "production") {
        console.debug("RunFlowGraph overlay positions", Object.keys(nodes).length);
      }
    };

    renderer.on("afterRender", updateOverlay);

    fitCameraToBounds(renderer, bounds, host);
    renderer.refresh();
    updateOverlay();

    prepareCanvas(host);

    sigmaRef.current = renderer;
    graphRef.current = graph;

    return () => {
      disposed = true;
      if (sigmaRef.current) {
        sigmaRef.current.kill();
        sigmaRef.current = null;
      }
      graphRef.current = null;
    };
  }, [structure, seekTo, alignOverlay, orientation]);

  useEffect(() => {
    const graph = graphRef.current;
    const renderer = sigmaRef.current;
    if (!graph || !renderer) return;

    graph.forEachNode((node: string) => {
      const meta = graph.getNodeAttributes(node) as FlowNodeMeta;
      graph.setNodeAttribute(node, "highlighted", cursorSeq === meta.seq);
    });

    graph.forEachEdge((edge: string) => {
      const attrs = graph.getEdgeAttributes(edge) as FlowEdgeMeta;
      if (attrs.kind === "sequential") {
        const targetSeq = (graph.getNodeAttributes(graph.target(edge)) as FlowNodeMeta).seq;
        graph.setEdgeAttribute(edge, "highlighted", cursorSeq === targetSeq);
      } else {
        const sourceSeq = (graph.getNodeAttributes(graph.source(edge)) as FlowNodeMeta).seq;
        const targetSeq = (graph.getNodeAttributes(graph.target(edge)) as FlowNodeMeta).seq;
        graph.setEdgeAttribute(edge, "highlighted", cursorSeq === sourceSeq || cursorSeq === targetSeq);
      }
    });

    renderer.refresh();
  }, [cursorSeq]);

  const handleClickNodeCard = useCallback(
    (seq: number) => {
      seekTo(seq);
    },
    [seekTo]
  );

  const overlayNodes = structure.nodes;

  if (!overlayNodes.length) {
    return (
      <div className="flex min-h-[280px] flex-1 items-center justify-center text-sm text-foreground/60">
        Trigger a run to visualize its flow.
      </div>
    );
  }

  const hasPositions = overlayNodes.some((node) => Boolean(nodePositions[node.id]));

  return (
    <div ref={containerRef} className="relative flex min-h-[320px] flex-1">
      <div ref={canvasRef} className="absolute inset-0" />
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-4 top-4 rounded bg-background/80 px-3 py-1 text-xs uppercase tracking-wide text-foreground/60">
          Execution Flow Graph · {overlayNodes.length} steps
        </div>
        {onExpand ? (
          <div className="absolute right-4 top-4 pointer-events-auto">
            <button
              type="button"
              className="rounded border border-white/20 bg-background/80 px-3 py-1 text-xs uppercase tracking-wide text-foreground/70 shadow-sm transition-colors hover:border-white/40"
              onClick={onExpand}
            >
              Expand
            </button>
          </div>
        ) : null}
        {!hasPositions ? (
          <div className="flex h-full w-full items-center justify-center text-sm text-foreground/50">
            Preparing layout…
          </div>
        ) : null}
        <FlowProgress
          className={
            orientation === "vertical"
              ? "absolute left-6 top-20 bottom-20 flex items-center pointer-events-auto"
              : "absolute bottom-8 left-1/2 -translate-x-1/2 flex pointer-events-auto"
          }
          nodes={overlayNodes}
          orientation={orientation}
          cursorSeq={cursorSeq}
          onSelect={handleClickNodeCard}
        />
        <FlowEdges
          edges={structure.edges}
          nodePositions={nodePositions}
          containerSize={containerSize}
          nodes={overlayNodes}
          cursorSeq={cursorSeq}
        />
        {overlayNodes.map((node) => {
          const position = nodePositions[node.id];
          if (!position) return null;
          const selected = cursorSeq === node.seq;
          return (
            <NodeCard
              key={node.id}
              node={node}
              position={position}
              selected={selected}
              onClick={handleClickNodeCard}
            />
          );
        })}
        {retryBadges.map((badge) => (
          <RetryBadge key={badge.id} left={badge.left} top={badge.top} count={badge.retryCount} />
        ))}
      </div>
    </div>
  );
}

function FlowProgress({
  nodes,
  orientation,
  cursorSeq,
  onSelect,
  className
}: {
  nodes: FlowNodeMeta[];
  orientation: "vertical" | "horizontal";
  cursorSeq: number | null;
  onSelect: (seq: number) => void;
  className: string;
}) {
  const ordered = useMemo(() => nodes.slice().sort((a, b) => a.seq - b.seq), [nodes]);
  if (!ordered.length) return null;

  const containerClasses = clsx(
    "flex items-center",
    orientation === "vertical" ? "flex-col" : "flex-row"
  );

  const containerStyle = orientation === "vertical"
    ? { height: "100%", justifyContent: "center" }
    : { width: "100%", justifyContent: "center" };

  return (
    <div className={clsx("flex", className)}>
      <div className={containerClasses} style={containerStyle}>
        {ordered.map((node, index) => {
          const isActive = cursorSeq === node.seq;
          const isLast = index === ordered.length - 1;
          const color = nodeStrokeForStatus(node.status);
          const buttonClasses = clsx(
            "relative flex items-center justify-center rounded-full border",
            isActive ? "border-primary ring-2 ring-primary/60" : "border-white/30"
          );

          const connectorClasses = clsx(
            "flex-shrink-0 bg-white/20",
            orientation === "vertical" ? "w-px" : "h-px"
          );

          const connectorStyle = orientation === "vertical"
            ? { height: MINI_GAP }
            : { width: MINI_GAP };

          return (
            <Fragment key={node.id}>
              <button
                type="button"
                className={buttonClasses}
                style={{ width: MINI_NODE_SIZE, height: MINI_NODE_SIZE }}
                onClick={() => onSelect(node.seq)}
              >
                <span
                  className="block h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: color }}
                />
              </button>
              {!isLast ? <div className={connectorClasses} style={connectorStyle} /> : null}
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}

function FlowEdges({
  edges,
  nodePositions,
  containerSize,
  nodes,
  cursorSeq
}: {
  edges: FlowEdgeMeta[];
  nodePositions: Record<string, NodePosition>;
  containerSize: { width: number; height: number };
  nodes: FlowNodeMeta[];
  cursorSeq: number | null;
}) {
  const nodeMap = useMemo(() => {
    const map = new Map<string, FlowNodeMeta>();
    nodes.forEach((node) => {
      map.set(node.id, node);
    });
    return map;
  }, [nodes]);

  if (!containerSize.width || !containerSize.height) return null;

  return (
    <svg className="absolute inset-0 pointer-events-none" width={containerSize.width} height={containerSize.height}>
      {edges.map((edge) => {
        const source = nodePositions[edge.source];
        const target = nodePositions[edge.target];
        if (!source || !target) {
          return null;
        }

        const sourceMeta = nodeMap.get(edge.source);
        const targetMeta = nodeMap.get(edge.target);
        let isHighlighted = false;
        if (edge.kind === "sequential" && targetMeta) {
          isHighlighted = cursorSeq === targetMeta.seq;
        }
        if (edge.kind === "retry" && sourceMeta && targetMeta) {
          isHighlighted = cursorSeq === sourceMeta.seq || cursorSeq === targetMeta.seq;
        }

        const stroke = edge.kind === "retry" ? "#f87171" : isHighlighted ? "#38bdf8" : "#475569";
        const strokeWidth = edge.kind === "retry" ? (isHighlighted ? 3 : 2.4) : isHighlighted ? 3 : 2;

        return (
          <line
            key={edge.id}
            x1={source.left}
            y1={source.top}
            x2={target.left}
            y2={target.top}
            stroke={stroke}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={0.85}
          />
        );
      })}
    </svg>
  );
}

export default RunFlowGraph;

function nodeStrokeForStatus(status: TimelineStatus): string {
  switch (status) {
    case "success":
      return "#34d399";
    case "failure":
      return "#f97316";
    default:
      return "#94a3b8";
  }
}

function buildFlowStructure(steps: RunEnvelope[]): FlowStructure {
  const ordered = [...steps].sort((a, b) => a.seq - b.seq);
  const nodes: FlowNodeMeta[] = [];
  const nodeMap = new Map<number, FlowNodeMeta>();

  ordered.forEach((envelope) => {
    const node = buildNodeMeta(envelope);
    nodes.push(node);
    nodeMap.set(envelope.seq, node);
  });
  const edges: FlowEdgeMeta[] = [];

  for (let i = 0; i < ordered.length - 1; i += 1) {
    const current = ordered[i];
    const next = ordered[i + 1];
    edges.push({
      id: `seq-${current.seq}-${next.seq}`,
      source: String(current.seq),
      target: String(next.seq),
      kind: "sequential"
    });
  }

  const retryOrigins = new Map<string, { originSeq: number; attempts: number }>();

  ordered.forEach((envelope) => {
    const node = nodeMap.get(envelope.seq);
    if (!node) return;
    const signature = stepSignature(envelope);

    if (!signature) {
      return;
    }

    const existing = retryOrigins.get(signature);

    if (node.status === "failure") {
      if (!existing) {
        retryOrigins.set(signature, { originSeq: envelope.seq, attempts: 0 });
      } else {
        const retryCount = existing.attempts + 1;
        edges.push({
          id: `retry-${existing.originSeq}-${envelope.seq}-${retryCount}`,
          source: String(envelope.seq),
          target: String(existing.originSeq),
          kind: "retry",
          retryCount
        });
        retryOrigins.set(signature, { originSeq: existing.originSeq, attempts: retryCount });
      }
    } else if (existing) {
      const retryCount = existing.attempts + 1;
      edges.push({
        id: `retry-${existing.originSeq}-${envelope.seq}-${retryCount}`,
        source: String(envelope.seq),
        target: String(existing.originSeq),
        kind: "retry",
        retryCount
      });
      retryOrigins.delete(signature);
    }
  });

  return { nodes, edges };
}

function buildNodeMeta(envelope: RunEnvelope): FlowNodeMeta {
  const { step } = envelope;
  const seqId = String(envelope.seq);

  if (step.kind === "log_entry") {
    if (step.entryType === "agent") {
      const payload = step.payload as Record<string, unknown> | undefined;
      const summary = summarizeAgentPayload(payload);
      return {
        id: seqId,
        seq: envelope.seq,
        kind: "agent",
        title: summary.actionLabel,
        subtitle: summary.actorLabel,
        detail: summary.detailLabel ?? summary.reasonLabel,
        durationLabel: summary.duration != null ? `${summary.duration} ms` : undefined,
        status: summary.status
      };
    }
    if (step.entryType === "tool") {
      const payload = step.payload as Record<string, unknown> | undefined;
      const summary = summarizeToolPayload(payload);
      return {
        id: seqId,
        seq: envelope.seq,
        kind: "tool",
        title: summary.toolLabel,
        subtitle: summary.actorLabel ?? "Tool Execution",
        detail: summary.detailLabel ?? summary.statusLabel,
        durationLabel: summary.duration != null ? `${summary.duration} ms` : undefined,
        status: summary.status
      };
    }
    return {
      id: seqId,
      seq: envelope.seq,
      kind: "system",
      title: `Log · ${String(step.entryType)}`,
      detail: "Inspect details for payload",
      status: "unknown"
    };
  }

  const summary = describeNonLogStep(step);
  return {
    id: seqId,
    seq: envelope.seq,
    kind: "system",
    title: summary.label,
    detail: summary.detail,
    status: "unknown"
  };
}

function stepSignature(envelope: RunEnvelope): string | null {
  const { step } = envelope;
  if (step.kind !== "log_entry") {
    return null;
  }

  const payload = step.payload as Record<string, unknown> | undefined;

  if (step.entryType === "tool") {
    const toolKey = typeof payload?.tool_key === "string" ? payload?.tool_key : "tool";
    const agentKey = typeof payload?.agent_key === "string" ? payload?.agent_key : "agent";
    return `tool:${agentKey}:${toolKey}`;
  }
  if (step.entryType === "agent") {
    const agentKey = typeof payload?.agent_key === "string" ? payload?.agent_key : "agent";
    const action = typeof payload?.decision_full === "object" && payload?.decision_full
      ? (payload.decision_full as { action?: string }).action
      : undefined;
    const fallback = typeof payload?.decision === "object" && payload?.decision
      ? (payload.decision as { action?: string }).action
      : undefined;
    const actionKey = (action ?? fallback ?? "action").toString().toLowerCase();
    return `agent:${agentKey}:${actionKey}`;
  }
  return `log:${String(step.entryType)}`;
}

function NodeCard({
  node,
  position,
  selected,
  onClick
}: {
  node: FlowNodeMeta;
  position: NodePosition;
  selected: boolean;
  onClick: (seq: number) => void;
}) {
  return (
    <button
      type="button"
      className={clsx(
        "pointer-events-auto absolute -translate-x-1/2 -translate-y-1/2 rounded-md border px-3 py-2 text-left shadow-lg transition-transform",
        selected ? "border-primary/80 bg-background/95 ring-2 ring-primary/60" : "border-white/10 bg-background/80 hover:-translate-y-1",
        node.kind === "tool" && "backdrop-blur"
      )}
      style={{ left: position.left, top: position.top, width: NODE_WIDTH - 20 }}
      onClick={() => onClick(node.seq)}
    >
      <div className="flex items-center gap-2">
        <span className={clsx("flex h-8 w-8 items-center justify-center rounded-full border", iconRingClasses(node.kind))}>
          {renderNodeIcon(node.kind)}
        </span>
        <div className="flex-1 text-xs text-foreground/80">
          <div className="flex items-center justify-between font-semibold">
            <span className="font-mono">Step {node.seq}</span>
            <span className="text-foreground/50">{node.status.toUpperCase()}</span>
          </div>
          <div className="mt-0.5 flex flex-col text-foreground/70">
            <span>{node.title}</span>
            {node.subtitle ? <span className="text-[10px] text-foreground/50">{node.subtitle}</span> : null}
          </div>
        </div>
      </div>
    </button>
  );
}

function initializeRenderer(graph: Graph, host: HTMLElement, seekTo: (seq: number) => void): Sigma {
  const renderer = new Sigma(graph as any, host, {
    allowInvalidContainer: false,
    renderEdgeLabels: false,
    enableEdgeHoverEvents: true,
    nodeReducer: (node: string, data: any) => {
      return {
        ...data,
        hidden: true,
        size: 1,
        color: "rgba(0,0,0,0)",
        label: undefined
      };
    },
    edgeReducer: (edge: string, data: any) => {
      if (data.kind === "retry") {
        return {
          ...data,
          size: data.highlighted ? 3.2 : 2.4,
          color: "#f87171"
        };
      }
      return {
        ...data,
        size: data.highlighted ? 3 : 2,
        color: data.highlighted ? "#38bdf8" : "#475569"
      };
    }
  } as any);

  renderer.on("clickNode", ({ node }) => {
    const meta = graph.getNodeAttributes(node) as FlowNodeMeta;
    seekTo(meta.seq);
  });

  renderer.on("downNode", ({ node }) => {
    const meta = graph.getNodeAttributes(node) as FlowNodeMeta;
    seekTo(meta.seq);
  });

  return renderer;
}

function applyCaptors(renderer: Sigma) {
  try {
    const mouseCaptor = renderer.getMouseCaptor?.() as any;
    const touchCaptor = renderer.getTouchCaptor?.() as any;
    mouseCaptor?.setState?.({ enabled: false, enableDragging: false, enableWheel: false });
    touchCaptor?.setState?.({ enabled: false, enableDragging: false, enableWheel: false });
  } catch (error) {
    if (process.env.NODE_ENV !== "production") {
      console.debug("Failed to disable captors", error);
    }
  }
}

function prepareCanvas(host: HTMLElement) {
  const canvases = host.querySelectorAll("canvas");
  canvases.forEach((canvas) => {
    canvas.style.touchAction = "none";
  });
}

function RetryBadge({ left, top, count }: { left: number; top: number; count: number }) {
  return (
    <div
      className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-full border border-danger/50 bg-danger/80 px-2 py-0.5 text-[11px] font-semibold text-foreground shadow-md"
      style={{ left, top }}
    >
      Retry ×{count}
    </div>
  );
}

function iconRingClasses(kind: FlowNodeKind): string {
  switch (kind) {
    case "agent":
      return "border-primary/50 bg-primary/10 text-primary";
    case "tool":
      return "border-secondary/50 bg-secondary/10 text-secondary";
    default:
      return "border-foreground/20 bg-foreground/10 text-foreground/60";
  }
}

function renderNodeIcon(kind: FlowNodeKind) {
  switch (kind) {
    case "agent":
      return <RobotGlyph />;
    case "tool":
      return <WrenchGlyph />;
    default:
      return <PulseGlyph />;
  }
}

function RobotGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="5" y="7" width="14" height="10" rx="2" />
      <circle cx="9" cy="12" r="1.2" />
      <circle cx="15" cy="12" r="1.2" />
      <path d="M9 16h6" />
      <path d="M12 5V3" />
      <path d="M7 5h10" />
    </svg>
  );
}

function WrenchGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M14.5 5.5a3.5 3.5 0 0 1-4.9 4.9L5 15v4h4l4.4-4.4a3.5 3.5 0 0 1 4.9-4.9L14.5 5.5z" />
      <circle cx="19" cy="5" r="2" />
    </svg>
  );
}

function PulseGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 12h4l2-7 4 14 2-7h6" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function fitCameraToBounds(renderer: Sigma, bounds: GraphBounds, host: HTMLElement) {
  const camera = renderer.getCamera();
  const margin = 64;
  const width = Math.max(bounds.maxX - bounds.minX, 1);
  const height = Math.max(bounds.maxY - bounds.minY, 1);
  const graphWidth = width + margin;
  const graphHeight = height + margin;
  const viewportWidth = host.clientWidth || graphWidth;
  const viewportHeight = host.clientHeight || graphHeight;
  const ratio = Math.max(graphWidth / viewportWidth, graphHeight / viewportHeight, 1);
  const centerX = (bounds.minX + bounds.maxX) / 2;
  const centerY = (bounds.minY + bounds.maxY) / 2;

  camera.setState({
    x: Number.isFinite(centerX) ? centerX : 0,
    y: Number.isFinite(centerY) ? centerY : 0,
    ratio
  });
}
