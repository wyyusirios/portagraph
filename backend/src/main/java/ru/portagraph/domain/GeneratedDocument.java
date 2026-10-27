package ru.portagraph.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;

/**
 * Автоматически сформированный документ: архитектурное описание, онбординг-гайд,
 * карточка сервиса. Создаётся как черновик и подтверждается человеком.
 */
@Entity
@Table(name = "generated_documents")
@Getter
@Setter
@NoArgsConstructor
public class GeneratedDocument {

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
    private DocumentType type;

    @Column(nullable = false, length = 300)
    private String title;

    @Column(name = "content_md", nullable = false, columnDefinition = "text")
    private String contentMd;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private DocumentStatus status = DocumentStatus.DRAFT;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "approved_by")
    private User approvedBy;

    @Column(name = "approved_at")
    private Instant approvedAt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt = Instant.now();

    public void approve(User architect) {
        if (status == DocumentStatus.OUTDATED) {
            throw new IllegalStateException("Документ устарел: сформируйте его заново по свежему графу");
        }
        this.status = DocumentStatus.APPROVED;
        this.approvedBy = architect;
        this.approvedAt = Instant.now();
    }
}
