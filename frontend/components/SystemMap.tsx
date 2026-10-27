'use client';

import { useEffect, useMemo, useState } from 'react';
import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node, MarkerType } from '@xyflow/react';
import dagre from '@dagrejs/dagre';
import '@xyflow/react/dist/style.css';
import { api, type GraphView, type NodeType } from '@/lib/api';

const COLORS: Partial<Record<NodeType, string>> = {
  SERVICE: '#3b5bdb', DATABASE: '#0ca678', MESSAGE_QUEUE: '#f08c00', EXTERNAL_SYSTEM: '#868e96',
  REPOSITORY: '#5f3dc4', MODULE: '#1971c2', CLASS: '#495057',
};

/** Автоматическая раскладка графа слева направо (dagre). */
function layout(view: GraphView): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 90 });
  g.setDefaultEdgeLabel(() => ({}));
  view.nodes.forEach((n) => g.setNode(n.id, { width: 180, height: 48 }));
  view.edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);

  const nodes: Node[] = view.nodes.map((n) => {
    const p = g.node(n.id);
    return {
      id: n.id,
      position: { x: p.x - 90, y: p.y - 24 },
      data: { label: n.label, type: n.type },
      style: { border: `2px solid ${COLORS[n.type] ?? '#adb5bd'}`, borderRadius: 10, width: 180, fontSize: 13 },
    };
  });
  const edges: Edge[] = view.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.type.replace('_', ' ').toLowerCase(),
    animated: e.type === 'PUBLISHES' || e.type === 'CONSUMES',
    markerEnd: { type: MarkerType.ArrowClosed },
    // связи с низкой уверенностью агента рисуются пунктиром — их стоит проверить
    style: { strokeDasharray: e.confidence < 0.7 ? '6 4' : undefined },
  }));
  return { nodes, edges };
}

interface Props {
  projectId: number;
  mode: 'overview' | 'detailed';
  onSelect?: (nodeId: string) => void;
}

export default function SystemMap({ projectId, mode, onSelect }: Props) {
  const [view, setView] = useState<GraphView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setView(null);
    api.graph(projectId, mode).then(setView).catch((e: Error) => setError(e.message));
  }, [projectId, mode]);

  const flow = useMemo(() => (view ? layout(view) : null), [view]);

  if (error) return <p className="p-6 text-red-600">{error}</p>;
  if (!flow) return <p className="p-6 text-slate-500">Загружаем граф…</p>;

  return (
    <div className="h-[calc(100vh-120px)] rounded-xl border bg-white">
      <ReactFlow nodes={flow.nodes} edges={flow.edges} fitView onNodeClick={(_, n) => onSelect?.(n.id)}>
        <Background />
        <MiniMap pannable zoomable />
        <Controls />
      </ReactFlow>
    </div>
  );
}
