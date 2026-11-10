package ru.portagraph.core;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import ru.portagraph.core.graph.ArchitectureGraph;
import ru.portagraph.core.graph.ArchitectureGraph.Edge;
import ru.portagraph.core.graph.ArchitectureGraph.Node;
import ru.portagraph.core.impact.ImpactAnalyzer;
import ru.portagraph.core.impact.ImpactAnalyzer.RiskLevel;

import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class ImpactAnalyzerTest {

    private ArchitectureGraph graph;

    /**
     * gateway → auth ← orders ← billing;  классы: OrderClient(orders) → AuthController(auth)
     */
    @BeforeEach
    void setUp() {
        graph = new ArchitectureGraph();
        graph.addNode(new Node(1, "SERVICE", "auth-service", null));
        graph.addNode(new Node(2, "SERVICE", "order-service", null));
        graph.addNode(new Node(3, "SERVICE", "billing-service", null));
        graph.addNode(new Node(4, "SERVICE", "api-gateway", null));
        graph.addNode(new Node(5, "CLASS", "AuthController", 1L));
        graph.addNode(new Node(6, "CLASS", "OrderClient", 2L));
        graph.addEdge(new Edge(2, 1, "CALLS_HTTP", 0.9));
        graph.addEdge(new Edge(4, 1, "CALLS_HTTP", 1.0));
        graph.addEdge(new Edge(3, 2, "CONSUMES", 0.8));
        graph.addEdge(new Edge(6, 5, "IMPORTS", 1.0));
    }

    @Test
    void findsDirectAndTransitiveConsumers() {
        var result = new ImpactAnalyzer(graph).analyze(List.of(1L), 3);
        var names = result.affected().stream().map(a -> a.node().name()).toList();
        assertEquals(List.of("api-gateway", "order-service", "billing-service"), names);
        assertEquals(2, result.affected().get(2).distance());
        assertEquals(List.of(1L, 2L, 3L), result.affected().get(2).path());
    }

    @Test
    void depthLimitsPropagation() {
        assertEquals(2, new ImpactAnalyzer(graph).analyze(List.of(1L), 1).affectedCount());
    }

    @Test
    void twoDirectServicesMeanHighRisk() {
        assertEquals(RiskLevel.HIGH, new ImpactAnalyzer(graph).analyze(List.of(1L), 3).risk());
    }

    @Test
    void leafChangeIsLowRisk() {
        var result = new ImpactAnalyzer(graph).analyze(List.of(4L), 3);
        assertEquals(0, result.affectedCount());
        assertEquals(RiskLevel.LOW, result.risk());
    }

    @Test
    void rejectsEmptySelectionAndUnknownNode() {
        var analyzer = new ImpactAnalyzer(graph);
        assertThrows(IllegalArgumentException.class, () -> analyzer.analyze(List.of(), 2));
        assertThrows(java.util.NoSuchElementException.class, () -> analyzer.analyze(List.of(99L), 2));
    }

    @Test
    void overviewLiftsClassEdgesToServices() {
        ArchitectureGraph overview = graph.collapseTo(Set.of("SERVICE"));
        assertEquals(4, overview.nodes().size());
        assertTrue(overview.dependenciesOf(2).stream()
                .anyMatch(e -> e.to() == 1 && e.type().equals("IMPORTS")));
    }
}
