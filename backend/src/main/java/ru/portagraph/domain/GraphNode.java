package ru.portagraph.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.util.HashMap;
import java.util.Map;

/**
 * Узел единого графа архитектуры: репозиторий, сервис, модуль, класс, сущность,
 * API-эндпоинт, база данных и т.д. Иерархия задаётся полем {@code parent}.
 */
@Entity
@Table(name = "graph_nodes")
@Getter
@Setter
@NoArgsConstructor
public class GraphNode {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id")
    private Project project;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "run_id")
    private AnalysisRun run;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private NodeType type;

    @Column(nullable = false, length = 300)
    private String name;

    @Column(name = "qualified_name", length = 1000)
    private String qualifiedName;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "repository_id")
    private GitRepository repository;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "source_file_id")
    private SourceFile sourceFile;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "parent_id")
    private GraphNode parent;

    /** Краткое описание назначения, сформированное агентом. */
    @Column(length = 2000)
    private String description;

    /** Уверенность агента в выводе, 0..1. */
    @Column(nullable = false)
    private double confidence = 1.0;

    /** Вывод подтверждён архитектором (human-in-the-loop). */
    @Column(nullable = false)
    private boolean verified;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> metadata = new HashMap<>();

    public GraphNode(Project project, AnalysisRun run, NodeType type, String name, String qualifiedName) {
        this.project = project;
        this.run = run;
        this.type = type;
        this.name = name;
        this.qualifiedName = qualifiedName;
    }
}
