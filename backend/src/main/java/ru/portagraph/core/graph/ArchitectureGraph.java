package ru.portagraph.core.graph;

import java.util.*;

/**
 * Единый граф архитектуры проекта в памяти.
 * <p>
 * Хранит узлы (репозитории, сервисы, модули, классы, сущности, API, базы данных)
 * и направленные рёбра зависимостей между ними. Используется для построения
 * визуализаций и для impact analysis. Класс не зависит от Spring и JPA,
 * поэтому его можно тестировать изолированно.
 */
public class ArchitectureGraph {

    private final Map<Long, Node> nodes = new LinkedHashMap<>();
    private final Map<Long, List<Edge>> outgoing = new HashMap<>();
    private final Map<Long, List<Edge>> incoming = new HashMap<>();

    /** Узел графа. */
    public record Node(long id, String type, String name, Long parentId) { }

    /** Направленное ребро: {@code from} зависит от {@code to}. */
    public record Edge(long from, long to, String type, double confidence) { }

    public void addNode(Node node) {
        nodes.put(node.id(), node);
        outgoing.putIfAbsent(node.id(), new ArrayList<>());
        incoming.putIfAbsent(node.id(), new ArrayList<>());
    }

    public void addEdge(Edge edge) {
        if (!nodes.containsKey(edge.from()) || !nodes.containsKey(edge.to())) {
            throw new IllegalArgumentException("Ребро ссылается на несуществующий узел: " + edge);
        }
        if (edge.from() == edge.to()) {
            return; // петли не несут информации о связях между компонентами
        }
        outgoing.get(edge.from()).add(edge);
        incoming.get(edge.to()).add(edge);
    }

    public Optional<Node> node(long id) {
        return Optional.ofNullable(nodes.get(id));
    }

    public Collection<Node> nodes() {
        return Collections.unmodifiableCollection(nodes.values());
    }

    /** Компоненты, от которых зависит узел. */
    public List<Edge> dependenciesOf(long id) {
        return Collections.unmodifiableList(outgoing.getOrDefault(id, List.of()));
    }

    /** Компоненты, которые зависят от узла (потребители). */
    public List<Edge> dependentsOf(long id) {
        return Collections.unmodifiableList(incoming.getOrDefault(id, List.of()));
    }

    public int edgeCount() {
        return outgoing.values().stream().mapToInt(List::size).sum();
    }

    /**
     * Обзорная карта: оставляет только узлы указанных типов (например, SERVICE и DATABASE)
     * и «поднимает» рёбра дочерних узлов до ближайшего видимого предка.
     */
    public ArchitectureGraph collapseTo(Set<String> visibleTypes) {
        ArchitectureGraph view = new ArchitectureGraph();
        Map<Long, Long> visibleAncestor = new HashMap<>();
        for (Node n : nodes.values()) {
            Long anc = findVisibleAncestor(n, visibleTypes);
            if (anc != null) {
                visibleAncestor.put(n.id(), anc);
                if (anc == n.id()) {
                    view.addNode(n);
                }
            }
        }
        Set<String> seen = new HashSet<>();
        for (List<Edge> list : outgoing.values()) {
            for (Edge e : list) {
                Long a = visibleAncestor.get(e.from());
                Long b = visibleAncestor.get(e.to());
                if (a != null && b != null && !a.equals(b) && seen.add(a + ">" + b + ":" + e.type())) {
                    view.addEdge(new Edge(a, b, e.type(), e.confidence()));
                }
            }
        }
        return view;
    }

    private Long findVisibleAncestor(Node n, Set<String> visibleTypes) {
        Node cur = n;
        int guard = 0;
        while (cur != null && guard++ < 64) {
            if (visibleTypes.contains(cur.type())) {
                return cur.id();
            }
            cur = cur.parentId() == null ? null : nodes.get(cur.parentId());
        }
        return null;
    }
}
