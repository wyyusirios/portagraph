package ru.portagraph.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

/**
 * Задача анализа проекта: загрузка, индексация, агентный анализ, построение графа.
 * Переходы между статусами проверяются методом {@link #moveTo(RunStatus)}.
 */
@Entity
@Table(name = "analysis_runs")
@Getter
@Setter
@NoArgsConstructor
public class AnalysisRun {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id")
    private Project project;

    @Enumerated(EnumType.STRING)
    @Column(name = "trigger_type", nullable = false, length = 20)
    private RunTrigger trigger;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private RunStatus status = RunStatus.QUEUED;

    /** Прогресс выполнения, 0–100 %. */
    @Column(nullable = false)
    private int progress;

    @Column(name = "started_at")
    private Instant startedAt;

    @Column(name = "finished_at")
    private Instant finishedAt;

    @Column(name = "error_message", length = 2000)
    private String errorMessage;

    /** Ключ архива артефактов анализа в S3/MinIO. */
    @Column(name = "artifact_key", length = 300)
    private String artifactKey;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> stats = new HashMap<>();

    private static final Map<RunStatus, Set<RunStatus>> ALLOWED = Map.of(
            RunStatus.QUEUED, EnumSet.of(RunStatus.FETCHING, RunStatus.CANCELLED),
            RunStatus.FETCHING, EnumSet.of(RunStatus.INDEXING, RunStatus.FAILED, RunStatus.CANCELLED),
            RunStatus.INDEXING, EnumSet.of(RunStatus.ANALYZING, RunStatus.FAILED, RunStatus.CANCELLED),
            RunStatus.ANALYZING, EnumSet.of(RunStatus.BUILDING_GRAPH, RunStatus.FAILED, RunStatus.CANCELLED),
            RunStatus.BUILDING_GRAPH, EnumSet.of(RunStatus.COMPLETED, RunStatus.FAILED),
            RunStatus.COMPLETED, EnumSet.noneOf(RunStatus.class),
            RunStatus.FAILED, EnumSet.of(RunStatus.QUEUED),
            RunStatus.CANCELLED, EnumSet.noneOf(RunStatus.class)
    );

    public AnalysisRun(Project project, RunTrigger trigger) {
        this.project = project;
        this.trigger = trigger;
    }

    public void moveTo(RunStatus next) {
        if (!ALLOWED.get(status).contains(next)) {
            throw new IllegalStateException("Недопустимый переход " + status + " → " + next);
        }
        if (status == RunStatus.QUEUED && next == RunStatus.FETCHING) {
            startedAt = Instant.now();
        }
        if (next == RunStatus.COMPLETED || next == RunStatus.FAILED || next == RunStatus.CANCELLED) {
            finishedAt = Instant.now();
        }
        if (next == RunStatus.COMPLETED) {
            progress = 100;
        }
        status = next;
    }

    public void fail(String message) {
        this.errorMessage = message;
        moveTo(RunStatus.FAILED);
    }

    public boolean isActive() {
        return status != RunStatus.COMPLETED && status != RunStatus.FAILED && status != RunStatus.CANCELLED;
    }
}
