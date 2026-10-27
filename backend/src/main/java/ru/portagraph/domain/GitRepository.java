package ru.portagraph.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;

/**
 * Подключённый Git-репозиторий. Роль и назначение репозитория пользователь
 * не задаёт — их определяет система (эвристика + агентный анализ).
 */
@Entity
@Table(name = "git_repositories",
        uniqueConstraints = @UniqueConstraint(columnNames = {"project_id", "url"}))
@Getter
@Setter
@NoArgsConstructor
public class GitRepository {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id")
    private Project project;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private GitProvider provider;

    @Column(nullable = false, length = 500)
    private String url;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(name = "default_branch", nullable = false, length = 100)
    private String defaultBranch = "main";

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "credential_id")
    private RepoCredential credential;

    @Enumerated(EnumType.STRING)
    @Column(name = "detected_role", nullable = false, length = 20)
    private RepositoryRole detectedRole = RepositoryRole.UNKNOWN;

    @Column(name = "role_confidence")
    private double roleConfidence;

    @Column(name = "purpose_summary", length = 2000)
    private String purposeSummary;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private RepositoryStatus status = RepositoryStatus.CONNECTED;

    @Column(name = "last_commit_sha", length = 64)
    private String lastCommitSha;

    @Column(name = "last_synced_at")
    private Instant lastSyncedAt;

    /** Секрет для проверки подписи webhook (HMAC-SHA256). */
    @Column(name = "webhook_secret", length = 128)
    private String webhookSecret;

    public GitRepository(GitProvider provider, String url, String name, String defaultBranch) {
        this.provider = provider;
        this.url = url;
        this.name = name;
        if (defaultBranch != null && !defaultBranch.isBlank()) {
            this.defaultBranch = defaultBranch;
        }
    }

    public void markSynced(String commitSha) {
        this.lastCommitSha = commitSha;
        this.lastSyncedAt = Instant.now();
        this.status = RepositoryStatus.READY;
    }
}
