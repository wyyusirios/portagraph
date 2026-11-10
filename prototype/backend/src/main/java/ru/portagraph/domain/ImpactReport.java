package ru.portagraph.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** Сохранённый результат impact analysis для предполагаемого изменения. */
@Entity
@Table(name = "impact_reports")
@Getter
@Setter
@NoArgsConstructor
public class ImpactReport {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id")
    private Project project;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id")
    private User author;

    @Column(name = "change_description", nullable = false, length = 2000)
    private String changeDescription;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "changed_node_ids", columnDefinition = "jsonb", nullable = false)
    private List<Long> changedNodeIds = new ArrayList<>();

    @Column(name = "max_depth", nullable = false)
    private int maxDepth;

    /** Затронутые компоненты: id узла, расстояние, вес влияния, путь. */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb", nullable = false)
    private List<Map<String, Object>> affected = new ArrayList<>();

    @Enumerated(EnumType.STRING)
    @Column(name = "risk_level", nullable = false, length = 20)
    private RiskLevel riskLevel;

    /** Пояснение агента: что проверить и кого предупредить. */
    @Column(columnDefinition = "text")
    private String recommendation;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt = Instant.now();
}
