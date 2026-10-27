package ru.portagraph.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.portagraph.domain.ChatSession;

import java.util.List;

public interface ChatSessionRepository extends JpaRepository<ChatSession, Long> {
    List<ChatSession> findByProjectIdAndUserIdOrderByCreatedAtDesc(Long projectId, Long userId);
}
