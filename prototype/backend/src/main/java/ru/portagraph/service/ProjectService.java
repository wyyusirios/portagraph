package ru.portagraph.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.portagraph.domain.*;
import ru.portagraph.repository.ProjectRepository;
import ru.portagraph.repository.UserRepository;

import java.util.List;

/** Создание проектов и управление участниками. */
@Service
public class ProjectService {

    private final ProjectRepository projects;
    private final UserRepository users;
    private final AccessGuard guard;

    public ProjectService(ProjectRepository projects, UserRepository users, AccessGuard guard) {
        this.projects = projects;
        this.users = users;
        this.guard = guard;
    }

    @Transactional
    public Project create(Long ownerId, String name, String description) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Название проекта обязательно");
        }
        User owner = users.findById(ownerId).orElseThrow(() -> new NotFoundException("Пользователь не найден"));
        return projects.save(new Project(name.strip(), description, owner));
    }

    @Transactional(readOnly = true)
    public List<Project> listForUser(Long userId) {
        return projects.findActiveForUser(userId);
    }

    @Transactional(readOnly = true)
    public Project get(Long projectId, Long userId) {
        guard.requireMember(projectId, userId);
        return projects.findById(projectId).orElseThrow(() -> new NotFoundException("Проект не найден"));
    }

    @Transactional
    public ProjectMember addMember(Long projectId, Long actorId, String email, ProjectRole role) {
        guard.requireOwner(projectId, actorId);
        if (role == ProjectRole.OWNER) {
            throw new IllegalArgumentException("У проекта может быть только один владелец");
        }
        Project p = get(projectId, actorId);
        User u = users.findByEmailIgnoreCase(email)
                .orElseThrow(() -> new NotFoundException("Пользователь " + email + " не зарегистрирован"));
        boolean already = p.getMembers().stream().anyMatch(m -> m.getUser().getId().equals(u.getId()));
        if (already) {
            throw new IllegalArgumentException("Пользователь уже участник проекта");
        }
        ProjectMember m = new ProjectMember(p, u, role);
        p.getMembers().add(m);
        return m;
    }

    @Transactional
    public void archive(Long projectId, Long actorId) {
        guard.requireOwner(projectId, actorId);
        get(projectId, actorId).setStatus(ProjectStatus.ARCHIVED);
    }
}
