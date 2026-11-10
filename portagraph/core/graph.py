"""Единый граф архитектуры проекта в памяти.

Ребро «A → B» означает «A зависит от B»: A вызывает B, читает его данные,
подписан на его события. Исключение — PUBLISHES: «сервис → топик» означает,
что сервис пишет в топик, и тогда уже топик (и его читатели) зависят от сервиса.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: типы рёбер, у которых зависимость направлена против стрелки
REVERSED_EDGE_TYPES = frozenset({"PUBLISHES"})


@dataclass(frozen=True)
class Node:
    id: int
    type: str
    name: str
    parent_id: int | None = None


@dataclass(frozen=True)
class Edge:
    source: int
    target: int
    type: str
    confidence: float = 1.0


@dataclass
class ArchitectureGraph:
    nodes: dict[int, Node] = field(default_factory=dict)
    outgoing: dict[int, list[Edge]] = field(default_factory=dict)
    incoming: dict[int, list[Edge]] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node
        self.outgoing.setdefault(node.id, [])
        self.incoming.setdefault(node.id, [])

    def add_edge(self, edge: Edge) -> None:
        if edge.source not in self.nodes or edge.target not in self.nodes:
            raise ValueError(f"Ребро ссылается на несуществующий узел: {edge}")
        if edge.source == edge.target:
            return  # петли не несут информации о связях между компонентами
        self.outgoing[edge.source].append(edge)
        self.incoming[edge.target].append(edge)

    def edges(self) -> list[Edge]:
        return [e for lst in self.outgoing.values() for e in lst]

    def dependencies_of(self, node_id: int) -> list[Edge]:
        return list(self.outgoing.get(node_id, []))

    def dependents_of(self, node_id: int) -> list[Edge]:
        return list(self.incoming.get(node_id, []))

    def affected_by(self, node_id: int) -> list[tuple[int, Edge]]:
        """Компоненты, которые затронет изменение узла, и рёбра, через которые это произойдёт."""
        out = [(e.source, e) for e in self.incoming.get(node_id, []) if e.type not in REVERSED_EDGE_TYPES]
        out += [(e.target, e) for e in self.outgoing.get(node_id, []) if e.type in REVERSED_EDGE_TYPES]
        return out

    def collapse_to(self, visible_types: set[str]) -> "ArchitectureGraph":
        """Обзорная карта: только узлы указанных типов, рёбра дочерних узлов
        «поднимаются» до ближайшего видимого предка, дубли объединяются."""
        view = ArchitectureGraph()
        ancestor: dict[int, int] = {}
        for n in self.nodes.values():
            a = self._visible_ancestor(n, visible_types)
            if a is not None:
                ancestor[n.id] = a
                if a == n.id:
                    view.add_node(n)
        best: dict[tuple[int, int, str], Edge] = {}
        for e in self.edges():
            a, b = ancestor.get(e.source), ancestor.get(e.target)
            if a is None or b is None or a == b:
                continue
            key = (a, b, e.type)
            if key not in best or e.confidence > best[key].confidence:
                best[key] = Edge(a, b, e.type, e.confidence)
        for e in best.values():
            view.add_edge(e)
        return view

    def _visible_ancestor(self, n: Node, visible: set[str]) -> int | None:
        cur, guard = n, 0
        while cur is not None and guard < 64:
            if cur.type in visible:
                return cur.id
            cur = self.nodes.get(cur.parent_id) if cur.parent_id is not None else None
            guard += 1
        return None
