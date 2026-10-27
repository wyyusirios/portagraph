package ru.portagraph.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Направленная связь: {@code source} зависит от {@code target}.
 * Поле {@code evidence} хранит доказательства — ссылки на строки кода, где связь найдена.
 */
@Entity
@Table(name = "graph_edges")
@Getter
@Setter
@NoArgsConstructor
public class GraphEdge {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id")
    private Project project;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "run_id")
    private AnalysisRun run;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "source_node_id")
    private GraphNode source;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "target_node_id")
    private GraphNode target;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private EdgeType type;

    @Column(nullable = false)
    private double confidence = 1.0;

    @Column(nullable = false)
    private boolean verified;

    /** Список доказательств: {"fileId": .., "line": .., "snippet": ".."}. */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private List<Map<String, Object>> evidence = new ArrayList<>();

    public GraphEdge(Project project, AnalysisRun run, GraphNode source, GraphNode target,
                     EdgeType type, double confidence) {
        this.project = project;
        this.run = run;
        this.source = source;
        this.target = target;
        this.type = type;
        this.confidence = confidence;
    }
}
