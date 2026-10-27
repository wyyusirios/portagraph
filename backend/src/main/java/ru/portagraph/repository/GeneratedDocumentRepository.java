package ru.portagraph.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import ru.portagraph.domain.GeneratedDocument;

import java.util.List;

public interface GeneratedDocumentRepository extends JpaRepository<GeneratedDocument, Long> {
    List<GeneratedDocument> findByProjectIdOrderByCreatedAtDesc(Long projectId);

    /** После нового анализа ранее подтверждённые документы помечаются устаревшими. */
    @Modifying
    @Query("update GeneratedDocument d set d.status = ru.portagraph.domain.DocumentStatus.OUTDATED where d.project.id = :projectId and d.run.id <> :runId")
    int markOutdated(Long projectId, Long runId);
}
