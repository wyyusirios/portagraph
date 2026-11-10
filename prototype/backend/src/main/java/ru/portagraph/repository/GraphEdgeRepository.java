package ru.portagraph.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.portagraph.domain.GraphEdge;

import java.util.List;

public interface GraphEdgeRepository extends JpaRepository<GraphEdge, Long> {
    List<GraphEdge> findByRunId(Long runId);
}
