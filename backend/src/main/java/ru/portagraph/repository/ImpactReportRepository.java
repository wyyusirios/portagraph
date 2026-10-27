package ru.portagraph.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.portagraph.domain.ImpactReport;

import java.util.List;

public interface ImpactReportRepository extends JpaRepository<ImpactReport, Long> {
    List<ImpactReport> findByProjectIdOrderByCreatedAtDesc(Long projectId);
}
