package ru.portagraph.service;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Component;
import ru.portagraph.domain.ProjectMember;
import ru.portagraph.repository.ProjectMemberRepository;

/** Проверка прав пользователя на действия в проекте (изоляция данных по проектам). */
@Component
public class AccessGuard {

    private final ProjectMemberRepository members;

    public AccessGuard(ProjectMemberRepository members) {
        this.members = members;
    }

    public ProjectMember requireMember(Long projectId, Long userId) {
        return members.findByProjectIdAndUserId(projectId, userId)
                .orElseThrow(() -> new AccessDeniedException("Нет доступа к проекту " + projectId));
    }

    public ProjectMember requireApprover(Long projectId, Long userId) {
        ProjectMember m = requireMember(projectId, userId);
        if (!m.canApprove()) {
            throw new AccessDeniedException("Подтверждать выводы может только архитектор или владелец проекта");
        }
        return m;
    }

    public ProjectMember requireOwner(Long projectId, Long userId) {
        ProjectMember m = requireMember(projectId, userId);
        if (!m.canManage()) {
            throw new AccessDeniedException("Действие доступно только владельцу проекта");
        }
        return m;
    }
}
