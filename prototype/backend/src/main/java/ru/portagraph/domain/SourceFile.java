package ru.portagraph.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;

/** Проиндексированный файл репозитория (код, README, OpenAPI, документация). */
@Entity
@Table(name = "source_files",
        uniqueConstraints = @UniqueConstraint(columnNames = {"repository_id", "path"}))
@Getter
@Setter
@NoArgsConstructor
public class SourceFile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "repository_id")
    private GitRepository repository;

    @Column(nullable = false, length = 1000)
    private String path;

    @Column(length = 40)
    private String language;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private FileKind kind;

    /** SHA содержимого: если не изменился, файл при синхронизации не переиндексируется. */
    @Column(name = "content_sha", nullable = false, length = 64)
    private String contentSha;

    @Column(name = "size_bytes", nullable = false)
    private long sizeBytes;

    /** Ключ очищенной от секретов копии файла в S3/MinIO. */
    @Column(name = "storage_key", length = 300)
    private String storageKey;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt = Instant.now();

    public SourceFile(GitRepository repository, String path, String language, FileKind kind,
                      String contentSha, long sizeBytes) {
        this.repository = repository;
        this.path = path;
        this.language = language;
        this.kind = kind;
        this.contentSha = contentSha;
        this.sizeBytes = sizeBytes;
    }
}
