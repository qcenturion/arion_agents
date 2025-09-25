"use client";

import { useEffect, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import Sigma from "sigma";
import { buildGraphModel, getEdgeColour } from "@/lib/graph";
import type { GraphPayload } from "@/lib/api/types";
import { fetchGraph } from "@/lib/api/graphs";
import { useSelectionStore } from "@/stores/useSelectionStore";

interface GraphViewerProps {
  graphVersionId: string;
  staticGraph?: GraphPayload | null;
  focusTraceId?: string;
  networkName?: string | null;
}

export function GraphViewer({ graphVersionId, staticGraph, focusTraceId, networkName }: GraphViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const selectNode = useSelectionStore((state) => state.selectNode);
  const selectEdge = useSelectionStore((state) => state.selectEdge);
  const selectedNodeId = useSelectionStore((state) => state.selectedNodeId);
  const selectedEdgeKey = useSelectionStore((state) => state.selectedEdgeKey);

  const { data: dynamicGraph } = useQuery({
    queryKey: ["graph", graphVersionId],
    queryFn: () => fetchGraph(graphVersionId),
    initialData: staticGraph,
    staleTime: 60_000
  });

  const model = useMemo(() => {
    if (!dynamicGraph) return null;
    return buildGraphModel(dynamicGraph);
  }, [dynamicGraph]);

  useEffect(() => {
    if (!containerRef.current || !model) {
      return undefined;
    }

    if (sigmaRef.current) {
      sigmaRef.current.kill();
      sigmaRef.current = null;
    }

    applyVisualAttributes(model.graph);

    const renderer = new Sigma(model.graph as any, containerRef.current, {
      renderEdgeLabels: false,
      allowInvalidContainer: false,
      enableEdgeHoverEvents: true,
      nodeReducer: (node: string, data: any) => {
        if (data.highlighted) {
          return {
            ...data,
            color: "#f97316",
            size: (data.size ?? 8) * 1.25
          };
        }
        return data;
      },
      edgeReducer: (edge: string, data: any) => {
        if (data.highlighted) {
          return {
            ...data,
            color: "#f59e0b",
            size: (data.size ?? 1.5) * 1.5
          };
        }
        return data;
      }
    } as any);

    renderer.on("clickNode", ({ node }) => {
      selectNode(node);
    });

    renderer.on("clickEdge", ({ edge }) => {
      selectEdge(edge);
    });

    renderer.on("downNode", ({ node }) => {
      selectNode(node);
    });

    renderer.getCamera().animate({ ratio: 1 }, { duration: 300 });

    sigmaRef.current = renderer;

    return () => {
      renderer.kill();
    };
  }, [model, selectEdge, selectNode]);

  useEffect(() => {
    if (!model || !sigmaRef.current) return;
    const { graph } = model;
    graph.forEachNode((node) => {
      graph.setNodeAttribute(node, "highlighted", node === selectedNodeId);
    });
    graph.forEachEdge((edge) => {
      graph.setEdgeAttribute(edge, "highlighted", edge === selectedEdgeKey);
    });
    sigmaRef.current.refresh();
  }, [model, selectedNodeId, selectedEdgeKey]);

  const showOverlay = Boolean(networkName || focusTraceId);

  return (
    <div className="relative h-full min-h-[320px] w-full">
      <div ref={containerRef} className="absolute inset-0" />
      {showOverlay ? (
        <div className="pointer-events-none absolute left-4 top-4 flex flex-col gap-2">
          {networkName ? (
            <div className="rounded bg-background/80 px-3 py-1 text-xs uppercase tracking-wide text-foreground/60">
              Network · {networkName}
            </div>
          ) : null}
          {focusTraceId ? (
            <div className="rounded bg-background/80 px-3 py-1 text-xs text-foreground/70">
              Trace {focusTraceId}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function applyVisualAttributes(graph: any) {
  graph.forEachNode((node: string, attributes: any) => {
    graph.setNodeAttribute(node, "size", attributes.pinned ? 24 : 16);
    graph.setNodeAttribute(node, "label", cleanNodeLabel(attributes));
    graph.setNodeAttribute(node, "color", getNodeColour(attributes.type));
  });

  graph.forEachEdge((edge: string, attributes: any) => {
    graph.setEdgeAttribute(edge, "size", 1.5);
    graph.setEdgeAttribute(edge, "color", getEdgeColour(attributes.type));
  });
}

function cleanNodeLabel(attributes: any): string {
  const raw = typeof attributes?.label === "string" ? attributes.label : "";
  if (!raw) {
    return "";
  }

  const agentNameCandidates = [
    attributes?.agent_display_name,
    attributes?.agentDisplayName,
    attributes?.agent_name,
    attributes?.agentName
  ];
  const agentName = agentNameCandidates.find((value) => typeof value === "string" && value.trim().length > 0);

  const lines = raw.split(/\r?\n/);
  const cleaned: string[] = [];

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      cleaned.push(line);
      return;
    }
    if (/^action:\s*tool$/i.test(trimmed)) {
      return;
    }
    if (/^network:/i.test(trimmed)) {
      return;
    }
    if (/^agent:\s*$/i.test(trimmed) && agentName) {
      cleaned.push(`Agent: ${agentName}`);
      return;
    }
    cleaned.push(line);
  });

  return cleaned.join("\n").replace(/\n+$/g, "");
}

function getNodeColour(type: string) {
  switch (type) {
    case "task":
      return "#38bdf8";
    case "decision":
      return "#f97316";
    case "subprocess":
      return "#a855f7";
    default:
      return "#94a3b8";
  }
}
