package ru.portagraph.core.impact;

import ru.portagraph.core.graph.ArchitectureGraph;
import ru.portagraph.core.graph.ArchitectureGraph.Edge;
import ru.portagraph.core.graph.ArchitectureGraph.Node;

import java.util.*;

/**
 * Impact analysis: оценивает, какие компоненты затронет изменение выбранных узлов.
 * <p>
 * Алгоритм — обход графа в ширину по обратным рёбрам (от изменяемого узла к его
 * потребителям) с ограничением глубины. Вклад каждого пути ослабляется с расстоянием
 * и с уверенностью ребра, найденного агентом.
 */
public class ImpactAnalyzer {

    /** Затухание влияния на каждом шаге удаления от источника изменения. */
    private static final double DECAY = 0.6;

    private final ArchitectureGraph graph;

    public ImpactAnalyzer(ArchitectureGraph graph) {
        this.graph = Objects.requireNonNull(graph);
    }

    /** Затронутый компонент. */
    public record AffectedComponent(Node node, int distance, double score, List<Long> path) { }

    /** Итог анализа. */
    public record ImpactResult(List<Long> changedNodeIds,
                               List<AffectedComponent> affected,
                               RiskLevel risk) {
        public int affectedCount() {
            return affected.size();
        }
    }

    public enum RiskLevel { LOW, MEDIUM, HIGH, CRITICAL }

    public ImpactResult analyze(Collection<Long> changedNodeIds, int maxDepth) {
        if (changedNodeIds == null || changedNodeIds.isEmpty()) {
            throw new IllegalArgumentException("Не выбрано ни одного изменяемого компонента");
        }
        if (maxDepth < 1) {
            throw new IllegalArgumentException("Глубина анализа должна быть не меньше 1");
        }
        Map<Long, AffectedComponent> best = new HashMap<>();
        Deque<AffectedComponent> queue = new ArrayDeque<>();

        for (Long id : changedNodeIds) {
            Node start = graph.node(id).orElseThrow(
                    () -> new NoSuchElementException("Узел " + id + " отсутствует в графе"));
            queue.add(new AffectedComponent(start, 0, 1.0, List.of(id)));
        }

        Set<Long> changed = new HashSet<>(changedNodeIds);
        while (!queue.isEmpty()) {
            AffectedComponent cur = queue.poll();
            if (cur.distance() >= maxDepth) {
                continue;
            }
            for (Edge e : graph.dependentsOf(cur.node().id())) {
                long consumer = e.from();
                if (changed.contains(consumer) || cur.path().contains(consumer)) {
                    continue; // исходные узлы и циклы не учитываем
                }
                double score = cur.score() * DECAY * Math.max(0.1, e.confidence());
                AffectedComponent prev = best.get(consumer);
                if (prev == null || score > prev.score()) {
                    List<Long> path = new ArrayList<>(cur.path());
                    path.add(consumer);
                    AffectedComponent next = new AffectedComponent(
                            graph.node(consumer).orElseThrow(), cur.distance() + 1, score, List.copyOf(path));
                    best.put(consumer, next);
                    queue.add(next);
                }
            }
        }

        List<AffectedComponent> affected = new ArrayList<>(best.values());
        affected.sort(Comparator.comparingDouble(AffectedComponent::score).reversed()
                .thenComparingInt(AffectedComponent::distance));
        return new ImpactResult(List.copyOf(changedNodeIds), affected, assessRisk(affected));
    }

    /** Риск зависит от числа прямо затронутых сервисов и общей «массы» влияния. */
    static RiskLevel assessRisk(List<AffectedComponent> affected) {
        long directServices = affected.stream()
                .filter(a -> a.distance() == 1 && "SERVICE".equals(a.node().type()))
                .count();
        double mass = affected.stream().mapToDouble(AffectedComponent::score).sum();
        if (directServices >= 4 || mass >= 4.0) return RiskLevel.CRITICAL;
        if (directServices >= 2 || mass >= 2.0) return RiskLevel.HIGH;
        if (!affected.isEmpty()) return RiskLevel.MEDIUM;
        return RiskLevel.LOW;
    }
}
