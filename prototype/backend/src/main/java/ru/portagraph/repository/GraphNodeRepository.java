package ru.portagraph.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.portagraph.domain.GraphNode;
import ru.portagraph.domain.NodeType;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

public interface GraphNodeRepository extends JpaRepository<GraphNode, Long> {
    List<GraphNode> findByRunId(Long runId);
    List<GraphNode> findByRunIdAndTypeIn(Long runId, Collection<NodeType> types);
    Optional<GraphNode> findByRunIdAndQualifiedName(Long runId, String qualifiedName);
}
