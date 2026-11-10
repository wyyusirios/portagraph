"""Impact analysis: какие компоненты затронет изменение выбранных узлов.

Обход графа в ширину от изменяемых узлов к их потребителям. На каждом шаге вес
влияния умножается на коэффициент затухания DECAY и на уверенность связи:

    вес(потребитель) = вес(узел) × DECAY × max(0,1; уверенность связи)
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .graph import ArchitectureGraph, Node

DECAY = 0.6
MIN_DEPTH, MAX_DEPTH, DEFAULT_DEPTH = 1, 6, 3


@dataclass(frozen=True)
class AffectedComponent:
    node: Node
    distance: int
    score: float
    path: tuple[int, ...]
    via: str  # тип связи, по которой пришло влияние на последнем шаге


@dataclass(frozen=True)
class ImpactResult:
    changed: tuple[int, ...]
    affected: tuple[AffectedComponent, ...]
    risk: str
    total_weight: float
    direct_services: int


def analyze(graph: ArchitectureGraph, changed_ids, max_depth: int = DEFAULT_DEPTH) -> ImpactResult:
    changed = tuple(dict.fromkeys(int(i) for i in changed_ids))
    if not changed:
        raise ValueError("Не выбрано ни одного изменяемого компонента")
    if not MIN_DEPTH <= max_depth <= MAX_DEPTH:
        raise ValueError(f"Глубина анализа должна быть от {MIN_DEPTH} до {MAX_DEPTH}")
    for cid in changed:
        if cid not in graph.nodes:
            raise KeyError(f"Узел {cid} отсутствует в графе")

    best: dict[int, AffectedComponent] = {}
    queue = deque(AffectedComponent(graph.nodes[c], 0, 1.0, (c,), "") for c in changed)
    changed_set = set(changed)
    while queue:
        cur = queue.popleft()
        if cur.distance >= max_depth:
            continue
        for consumer, edge in graph.affected_by(cur.node.id):
            if consumer in changed_set or consumer in cur.path:
                continue  # исходные узлы и циклы не учитываем
            score = cur.score * DECAY * max(0.1, edge.confidence)
            prev = best.get(consumer)
            if prev is None or score > prev.score:
                nxt = AffectedComponent(graph.nodes[consumer], cur.distance + 1, score, cur.path + (consumer,), edge.type)
                best[consumer] = nxt
                queue.append(nxt)

    affected = sorted(best.values(), key=lambda a: (-a.score, a.distance, a.node.name))
    total = sum(a.score for a in affected)
    direct_services = sum(1 for a in affected if a.distance == 1 and a.node.type == "SERVICE")
    return ImpactResult(changed, tuple(affected), assess_risk(direct_services, total, len(affected)),
                        round(total, 4), direct_services)


def assess_risk(direct_services: int, total_weight: float, affected_count: int) -> str:
    """CRITICAL — от 4 прямо затронутых сервисов или суммарный вес ≥ 4;
    HIGH — от 2 сервисов или вес ≥ 2; MEDIUM — затронут хотя бы один компонент."""
    if direct_services >= 4 or total_weight >= 4.0:
        return "CRITICAL"
    if direct_services >= 2 or total_weight >= 2.0:
        return "HIGH"
    if affected_count:
        return "MEDIUM"
    return "LOW"
