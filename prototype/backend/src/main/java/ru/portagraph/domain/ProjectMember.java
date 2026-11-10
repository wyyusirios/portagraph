package ru.portagraph.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;

/** Участник проекта и его роль (определяет права доступа). */
@Entity
@Table(name = "project_members",
        uniqueConstraints = @UniqueConstraint(columnNames = {"project_id", "user_id"}))
@Getter
@Setter
@NoArgsConstructor
public class ProjectMember {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id")
    private Project project;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id")
    private User user;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ProjectRole role;

    @Column(name = "joined_at", nullable = false)
    private Instant joinedAt = Instant.now();

    public ProjectMember(Project project, User user, ProjectRole role) {
        this.project = project;
        this.user = user;
        this.role = role;
    }

    /** Может ли участник подтверждать AI-выводы и менять граф. */
    public boolean canApprove() {
        return role == ProjectRole.OWNER || role == ProjectRole.ARCHITECT;
    }

    /** Может ли участник подключать репозитории и управлять участниками. */
    public boolean canManage() {
        return role == ProjectRole.OWNER;
    }
}
