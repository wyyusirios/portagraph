package ru.portagraph.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.portagraph.domain.AnalysisRun;
import ru.portagraph.domain.RunStatus;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

public interface AnalysisRunRepository extends JpaRepository<AnalysisRun, Long> {
    Optional<AnalysisRun> findFirstByProjectIdAndStatusOrderByFinishedAtDesc(Long projectId, RunStatus status);
    boolean existsByProjectIdAndStatusIn(Long projectId, Collection<RunStatus> statuses);
    List<AnalysisRun> findTop10ByProjectIdOrderByIdDesc(Long projectId);
}
