package ru.portagraph.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;

/**
 * Токен доступа к Git-хостингу. Хранится только в зашифрованном виде (AES-GCM),
 * никогда не попадает в индекс, логи и запросы к LLM.
 */
@Entity
@Table(name = "repo_credentials")
@Getter
@Setter
@NoArgsConstructor
public class RepoCredential {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id")
    private Project project;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private GitProvider provider;

    @Column(name = "encrypted_token", nullable = false)
    private byte[] encryptedToken;

    @Column(length = 300)
    private String scopes;

    @Column(name = "expires_at")
    private Instant expiresAt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt = Instant.now();

    public boolean isExpired(Instant now) {
        return expiresAt != null && expiresAt.isBefore(now);
    }
}
