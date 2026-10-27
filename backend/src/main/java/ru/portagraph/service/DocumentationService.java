package ru.portagraph.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.portagraph.agent.AgentRuntime;
import ru.portagraph.domain.*;
import ru.portagraph.repository.GeneratedDocumentRepository;
import ru.portagraph.repository.GitRepositoryRepository;
import ru.portagraph.repository.GraphEdgeRepository;
import ru.portagraph.repository.GraphNodeRepository;
import ru.portagraph.repository.UserRepository;

import java.util.EnumSet;
import java.util.List;
import java.util.Set;

/** Автоматическое формирование архитектурных описаний и материалов для онбординга (UC-11). */
@Service
public class DocumentationService {

    private static final Set<NodeType> SUMMARY_TYPES = EnumSet.of(NodeType.SERVICE, NodeType.REPOSITORY,
            NodeType.MODULE, NodeType.DATABASE, NodeType.MESSAGE_QUEUE, NodeType.EXTERNAL_SYSTEM);

    private final GraphService graphs;
    private final GraphNodeRepository nodes;
    private final GraphEdgeRepository edges;
    private final GitRepositoryRepository repositories;
    private final GeneratedDocumentRepository documents;
    private final UserRepository users;
    private final AgentRuntime agent;
    private final AccessGuard guard;

    public DocumentationService(GraphService graphs, GraphNodeRepository nodes, GraphEdgeRepository edges,
                                GitRepositoryRepository repositories, GeneratedDocumentRepository documents,
                                UserRepository users, AgentRuntime agent, AccessGuard guard) {
        this.graphs = graphs;
        this.nodes = nodes;
        this.edges = edges;
        this.repositories = repositories;
        this.documents = documents;
        this.users = users;
        this.agent = agent;
        this.guard = guard;
    }

    @Transactional
    public GeneratedDocument generate(Long projectId, Long userId, DocumentType type) {
        guard.requireMember(projectId, userId);
        AnalysisRun run = graphs.latestRun(projectId);
        String markdown = agent.draftDocument(type.name(), summarize(projectId, run));
        if (markdown == null || markdown.isBlank()) {
            throw new IllegalStateException("Агент не смог сформировать документ");
        }
        GeneratedDocument doc = new GeneratedDocument();
        doc.setProject(run.getProject());
        doc.setRun(run);
        doc.setType(type);
        doc.setTitle(titleFor(type, run.getProject().getName()));
        doc.setContentMd(markdown);
        return documents.save(doc);
    }

    @Transactional
    public GeneratedDocument approve(Long projectId, Long userId, Long documentId) {
        guard.requireApprover(projectId, userId);
        GeneratedDocument doc = documents.findById(documentId)
                .filter(d -> d.getProject().getId().equals(projectId))
                .orElseThrow(() -> new NotFoundException("Документ не найден"));
        doc.approve(users.getReferenceById(userId));
        return doc;
    }

    @Transactional(readOnly = true)
    public List<GeneratedDocument> list(Long projectId, Long userId) {
        guard.requireMember(projectId, userId);
        return documents.findByProjectIdOrderByCreatedAtDesc(projectId);
    }

    /** Компактное текстовое описание графа для промпта агента. */
    String summarize(Long projectId, AnalysisRun run) {
        StringBuilder sb = new StringBuilder();
        sb.append("# Репозитории\n");
        for (GitRepository r : repositories.findByProjectId(projectId)) {
            sb.append("- ").append(r.getName()).append(" [").append(r.getDetectedRole()).append("]: ")
                    .append(r.getPurposeSummary() == null ? "назначение не определено" : r.getPurposeSummary())
                    .append('\n');
        }
        sb.append("# Компоненты\n");
        nodes.findByRunIdAndTypeIn(run.getId(), SUMMARY_TYPES).forEach(n -> sb.append("- ")
                .append(n.getType()).append(' ').append(n.getName())
                .append(n.isVerified() ? " (подтверждено)" : "")
                .append(n.getDescription() == null ? "" : ": " + n.getDescription()).append('\n'));
        sb.append("# Связи\n");
        edges.findByRunId(run.getId()).forEach(e -> sb.append("- ").append(e.getSource().getName())
                .append(" -").append(e.getType()).append("-> ").append(e.getTarget().getName()).append('\n'));
        return sb.toString();
    }

    private static String titleFor(DocumentType type, String project) {
        return switch (type) {
            case ARCHITECTURE_OVERVIEW -> "Архитектура системы «" + project + "»";
            case ONBOARDING_GUIDE -> "Онбординг: как устроен проект «" + project + "»";
            case SERVICE_CARD -> "Карточки сервисов проекта «" + project + "»";
        };
    }
}
