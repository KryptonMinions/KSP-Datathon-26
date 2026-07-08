"use client";

import { useMemo, useRef, useState } from "react";
import CytoscapeComponent from "react-cytoscapejs";
import type { Core, ElementDefinition, NodeSingular } from "cytoscape";
import type {
  NetworkGraphBlock as NetworkGraphBlockType,
  GraphNodeKind,
} from "@/lib/types/content-blocks";
import { EntityChip } from "@/components/shared/EntityChip";
import { CitationChip } from "@/components/shared/CitationChip";

const KIND_COLOR: Record<GraphNodeKind, string> = {
  person: "#28406b",
  gang: "#b8934a",
  phone: "#6b7280",
  address: "#6b7280",
};

/**
 * One shell-agnostic, fully interactive network graph — used identically in
 * MobileShell (390px bezel) and DesktopShell, per explicit product
 * direction. Pan/zoom/tap work the same in both; this deliberately
 * overrides steering-docs §6's "simplified on mobile" language for this
 * renderer only.
 */
export function NetworkGraphBlock({ block }: { block: NetworkGraphBlockType }) {
  const cyRef = useRef<Core | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const elements: ElementDefinition[] = useMemo(() => {
    const nodes: ElementDefinition[] = block.nodes.map((n) => ({
      data: {
        id: n.id,
        label: n.label,
        kind: n.kind,
        isCentral: n.id === block.centralNodeId,
      },
    }));
    const edges: ElementDefinition[] = block.edges.map((e, i) => ({
      data: {
        id: `edge-${i}`,
        source: e.source,
        target: e.target,
        label: e.label,
        firId: e.firId,
      },
    }));
    return [...nodes, ...edges];
  }, [block]);

  const stylesheet = useMemo(
    () => [
      {
        selector: "node",
        style: {
          label: "data(label)",
          "font-size": 10,
          "text-valign": "bottom" as const,
          "text-margin-y": 6,
          color: "var(--color-foreground, #1f2937)",
          "background-color": (ele: NodeSingular) =>
            KIND_COLOR[ele.data("kind") as GraphNodeKind] ?? "#6b7280",
          width: (ele: NodeSingular) => (ele.data("isCentral") ? 44 : 30),
          height: (ele: NodeSingular) => (ele.data("isCentral") ? 44 : 30),
          "border-width": (ele: NodeSingular) => (ele.data("isCentral") ? 3 : 0),
          "border-color": "#b8934a",
        },
      },
      {
        selector: "edge",
        style: {
          width: 1.5,
          "line-color": "#9ca3af",
          "target-arrow-shape": "none" as const,
          "curve-style": "bezier" as const,
          label: "data(label)",
          "font-size": 8,
          color: "#6b7280",
          "text-background-color": "#ffffff",
          "text-background-opacity": 1,
          "text-background-padding": 2,
        },
      },
    ],
    [],
  );

  const selectedNode = block.nodes.find((n) => n.id === selectedNodeId);

  return (
    <div className="space-y-2">
      <div className="h-80 w-full rounded-md border border-border bg-card sm:h-95">
        <CytoscapeComponent
          elements={elements}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          stylesheet={stylesheet as any}
          layout={{ name: "cose", animate: false, padding: 24 }}
          style={{ width: "100%", height: "100%" }}
          minZoom={0.5}
          maxZoom={3}
          userZoomingEnabled
          userPanningEnabled
          boxSelectionEnabled={false}
          cy={(cy) => {
            cyRef.current = cy;
            cy.off("tap", "node");
            cy.on("tap", "node", (event) => {
              setSelectedNodeId(event.target.id());
            });
          }}
        />
      </div>

      {selectedNode && (
        <div className="flex items-center gap-2">
          <EntityChip
            entity={{
              id: selectedNode.id,
              name: selectedNode.label,
              kind: selectedNode.kind,
              subtitle: selectedNode.status,
            }}
          />
        </div>
      )}

      {block.citations && block.citations.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {block.citations.map((citation, i) => (
            <CitationChip key={`${citation.firId}-${i}`} citation={citation} />
          ))}
        </div>
      )}
    </div>
  );
}
