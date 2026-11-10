package ru.portagraph.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.portagraph.domain.SourceFile;

import java.util.List;
import java.util.Optional;

public interface SourceFileRepository extends JpaRepository<SourceFile, Long> {
    Optional<SourceFile> findByRepositoryIdAndPath(Long repositoryId, String path);
    List<SourceFile> findByRepositoryId(Long repositoryId);
}
