package ru.portagraph.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.portagraph.domain.GitRepository;

import java.util.List;

public interface GitRepositoryRepository extends JpaRepository<GitRepository, Long> {
    List<GitRepository> findByProjectId(Long projectId);
    boolean existsByProjectIdAndUrl(Long projectId, String url);
}
