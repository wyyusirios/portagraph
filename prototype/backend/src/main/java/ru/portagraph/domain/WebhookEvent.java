package ru.portagraph.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;

/**
 * Событие push/merge от Git-хостинга. Хранение deliveryId защищает от повторной
 * обработки одного и того же события (идемпотентность).
 */
@Entity
@Table(name = "webhook_events",
        uniqueConstraints = @UniqueConstraint(columnNames = {"repository_id", "delivery_id"}))
@Getter
@Setter
@NoArgsConstructor
public class WebhookEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "repository_id")
    private GitRepository repository;

    @Column(name = "delivery_id", nullable = false, length = 100)
    private String deliveryId;

    @Column(name = "event_type", nullable = false, length = 50)
    private String eventType;

    @Column(length = 200)
    private String branch;

    @Column(name = "commit_sha", length = 64)
    private String commitSha;

    @Column(name = "received_at", nullable = false)
    private Instant receivedAt = Instant.now();

    @Column(nullable = false)
    private boolean processed;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "run_id")
    private AnalysisRun run;
}
