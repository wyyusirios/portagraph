package ru.portagraph.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.portagraph.agent.AgentRuntime;
import ru.portagraph.agent.AgentRuntime.*;
import ru.portagraph.core.analysis.DependencyExtractor;
import ru.portagraph.core.analysis.RepositoryRoleClassifier;
import ru.portagraph.core.analysis.SymbolExtractor;
import ru.portagraph.core.graph.ArchitectureGraph;
import ru.portagraph.core.indexing.CodeChunker.SymbolSpan;
import ru.portagraph.domain.*;
import ru.portagraph.repository.*;

import java.util.*;
import java.util.stream.Collectors;

/**
 * Построение единого графа архитектуры по нескольким репозиториям (UC-05, UC-06)
 * и выдача его представлений для визуализации (UC-07, UC-08).
 */
@Service
public class GraphService {

    /** Порог уверенности, ниже которого связь не попадает в граф. */
    static final double MIN_EDGE_CONFIDENCE = 0.35;

    private static final Set<NodeType> OVERVIEW_TYPES = EnumSet.of(
            NodeType.SERVICE, NodeType.DATABASE, NodeType.MESSAGE_QUEUE, NodeType.EXTERNAL_SYSTEM);

    private final AgentRuntime agent;
    private final GitRepositoryRepository repositories;
    private final SourceFileRepository files;
    private final GraphNodeRepository nodes;
    private final GraphEdgeRepository edges;
    private final AnalysisRunRepository runs;
    private final ArtifactStorage storage;
    private final AccessGuard guard;
    private final RepositoryRoleClassifier roleClassifier = new RepositoryRoleClassifier();
    private final SymbolExtractor symbols = new SymbolExtractor();

    public GraphService(AgentRuntime agent, GitRepositoryRepository repositories, SourceFileRepository files,
                        GraphNodeRepository nodes, GraphEdgeRepository edges, AnalysisRunRepository runs,
                        ArtifactStorage storage, AccessGuard guard) {
        this.agent = agent;
        this.repositories = repositories;
        this.files = files;
        this.nodes = nodes;
        this.edges = edges;
        this.runs = runs;
        this.storage = storage;
        this.guard = guard;
    }

    // ------------------------------------------------------------------ построение

    /** Агентный анализ репозиториев: роль, назначение, модули. */
    @Transactional
    public Map<Long, GraphNode> analyzeRepositories(AnalysisRun run) {
        Project project = run.getProject();
        GraphNode system = nodes.save(new GraphNode(project, run, NodeType.SYSTEM, project.getName(),
                "system:" + project.getId()));
        Map<Long, GraphNode> componentByRepo = new HashMap<>();

        for (GitRepository repo : repositories.findByProjectId(project.getId())) {
            List<SourceFile> repoFiles = files.findByRepositoryId(repo.getId());
            List<String> paths = repoFiles.stream().map(SourceFile::getPath).toList();

            RepositoryRoleClassifier.Classification guess = roleClassifier.classify(paths);
            RepositoryInsight insight = agent.describeRepository(new RepositoryContext(
                    repo.getName(), readText(repoFiles, FileKind.README), paths,
                    paths.stream().filter(p -> p.toLowerCase().contains("application")
                            || p.endsWith("main.go") || p.endsWith("main.py")).toList(),
                    readText(repoFiles, FileKind.API_SPEC)));

            RepositoryRole role = pickRole(guess, insight);
            repo.setDetectedRole(role);
            repo.setRoleConfidence(Math.max(guess.confidence(), insight.confidence()));
            repo.setPurposeSummary(insight.purpose());

            GraphNode repoNode = new GraphNode(project, run, NodeType.REPOSITORY, repo.getName(), "repo:" + repo.getId());
            repoNode.setParent(system);
            repoNode.setRepository(repo);
            repoNode.setDescription(insight.purpose());
            repoNode.setConfidence(repo.getRoleConfidence());
            nodes.save(repoNode);

            GraphNode component = repoNode;
            if (role == RepositoryRole.SERVICE || role == RepositoryRole.FRONTEND) {
                component = new GraphNode(project, run, NodeType.SERVICE, repo.getName(), "service:" + repo.getName());
                component.setParent(repoNode);
                component.setRepository(repo);
                component.setDescription(insight.purpose());
                component.setConfidence(insight.confidence());
                component.getMetadata().put("role", role.name());
                nodes.save(component);
            }
            componentByRepo.put(repo.getId(), component);

            for (ModuleInsight mi : Optional.ofNullable(insight.modules()).orElse(List.of())) {
                GraphNode module = new GraphNode(project, run, NodeType.MODULE, mi.name(),
                        "module:" + repo.getId() + ":" + mi.path());
                module.setParent(component);
                module.setRepository(repo);
                module.setDescription(mi.purpose());
                nodes.save(module);
            }
            addClassNodes(run, repo, repoFiles, component);
        }
        return componentByRepo;
    }

    /** Поиск межрепозиторных связей и их проверка агентом. */
    @Transactional
    public int linkRepositories(AnalysisRun run, Map<Long, GraphNode> componentByRepo) {
        Project project = run.getProject();
        List<GitRepository> repos = repositories.findByProjectId(project.getId());
        Map<String, GitRepository> byName = repos.stream()
                .collect(Collectors.toMap(r -> r.getName().toLowerCase(), r -> r, (a, b) -> a));
        DependencyExtractor extractor = new DependencyExtractor(byName.keySet(), byName.keySet());

        List<LinkCandidateDto> candidates = new ArrayList<>();
        Map<String, List<Map<String, Object>>> evidence = new HashMap<>();
        for (GitRepository repo : repos) {
            for (SourceFile f : files.findByRepositoryId(repo.getId())) {
                if (f.getKind() != FileKind.CODE && f.getKind() != FileKind.CONFIG
                        && f.getKind() != FileKind.BUILD_SCRIPT) continue;
                for (DependencyExtractor.LinkCandidate c : extractor.extract(f.getPath(), storage.getText(f.getStorageKey()))) {
                    candidates.add(new LinkCandidateDto(repo.getName(), c.type().name(), c.target(), c.evidence()));
                    evidence.computeIfAbsent(repo.getName() + "|" + c.target(), k -> new ArrayList<>())
                            .add(Map.of("fileId", f.getId(), "path", f.getPath(), "line", c.line(), "snippet", c.evidence()));
                }
            }
        }
        if (candidates.isEmpty()) return 0;

        Map<String, String> summaries = repos.stream().collect(Collectors.toMap(GitRepository::getName,
                r -> Objects.requireNonNullElse(r.getPurposeSummary(), ""), (a, b) -> a));
        int created = 0;
        for (LinkVerdict v : agent.verifyLinks(candidates, summaries)) {
            GitRepository from = byName.get(v.fromRepository().toLowerCase());
            GitRepository to = v.toRepository() == null ? null : byName.get(v.toRepository().toLowerCase());
            if (from == null || to == null || from.equals(to) || v.confidence() < MIN_EDGE_CONFIDENCE) continue;
            GraphEdge e = new GraphEdge(project, run, componentByRepo.get(from.getId()), componentByRepo.get(to.getId()),
                    mapEdgeType(v.type()), v.confidence());
            e.setEvidence(evidence.getOrDefault(from.getName() + "|" + to.getName().toLowerCase(), List.of()));
            edges.save(e);
            created++;
        }
        return created;
    }

    private void addClassNodes(AnalysisRun run, GitRepository repo, List<SourceFile> repoFiles, GraphNode parent) {
        for (SourceFile f : repoFiles) {
            if (f.getKind() != FileKind.CODE || f.getLanguage() == null) continue;
            for (SymbolSpan s : symbols.extract(f.getLanguage(), storage.getText(f.getStorageKey()))) {
                GraphNode n = new GraphNode(run.getProject(), run, NodeType.CLASS, s.name(),
                        "class:" + repo.getId() + ":" + f.getPath() + "#" + s.name());
                n.setParent(parent);
                n.setRepository(repo);
                n.setSourceFile(f);
                n.getMetadata().put("lines", s.startLine() + "-" + s.endLine());
                nodes.save(n);
            }
        }
    }

    // ------------------------------------------------------------------ чтение

    /** Граф последнего завершённого анализа в виде структуры для алгоритмов. */
    @Transactional(readOnly = true)
    public ArchitectureGraph loadGraph(Long projectId) {
        AnalysisRun run = latestRun(projectId);
        ArchitectureGraph g = new ArchitectureGraph();
        for (GraphNode n : nodes.findByRunId(run.getId())) {
            g.addNode(new ArchitectureGraph.Node(n.getId(), n.getType().name(), n.getName(),
                    n.getParent() == null ? null : n.getParent().getId()));
        }
        for (GraphEdge e : edges.findByRunId(run.getId())) {
            g.addEdge(new ArchitectureGraph.Edge(e.getSource().getId(), e.getTarget().getId(),
                    e.getType().name(), e.getConfidence()));
        }
        return g;
    }

    /** Обзорная карта системы: сервисы, БД, очереди, внешние системы. */
    @Transactional(readOnly = true)
    public ArchitectureGraph overview(Long projectId, Long userId) {
        guard.requireMember(projectId, userId);
        return loadGraph(projectId).collapseTo(OVERVIEW_TYPES.stream().map(Enum::name).collect(Collectors.toSet()));
    }

    /** Детальный граф: всё, включая модули и классы. */
    @Transactional(readOnly = true)
    public ArchitectureGraph detailed(Long projectId, Long userId) {
        guard.requireMember(projectId, userId);
        return loadGraph(projectId);
    }

    /** Подтверждение или исправление вывода агента архитектором. */
    @Transactional
    public GraphNode verifyNode(Long projectId, Long userId, Long nodeId, String correctedDescription) {
        guard.requireApprover(projectId, userId);
        GraphNode n = nodes.findById(nodeId).filter(x -> x.getProject().getId().equals(projectId))
                .orElseThrow(() -> new NotFoundException("Узел не найден"));
        if (correctedDescription != null && !correctedDescription.isBlank()) {
            n.setDescription(correctedDescription.strip());
        }
        n.setVerified(true);
        n.setConfidence(1.0);
        return n;
    }

    @Transactional(readOnly = true)
    public AnalysisRun latestRun(Long projectId) {
        return runs.findFirstByProjectIdAndStatusOrderByFinishedAtDesc(projectId, RunStatus.COMPLETED)
                .orElseThrow(() -> new NotFoundException("Для проекта ещё нет завершённого анализа"));
    }

    private String readText(List<SourceFile> repoFiles, FileKind kind) {
        return repoFiles.stream().filter(f -> f.getKind() == kind).findFirst()
                .map(f -> storage.getText(f.getStorageKey())).orElse("");
    }

    private static RepositoryRole pickRole(RepositoryRoleClassifier.Classification guess, RepositoryInsight insight) {
        try {
            RepositoryRole agentRole = RepositoryRole.valueOf(insight.role());
            return insight.confidence() >= guess.confidence() ? agentRole : RepositoryRole.valueOf(guess.role().name());
        } catch (IllegalArgumentException | NullPointerException e) {
            return RepositoryRole.valueOf(guess.role().name());
        }
    }

    private static EdgeType mapEdgeType(String linkType) {
        return switch (linkType) {
            case "CALLS_HTTP" -> EdgeType.CALLS_HTTP;
            case "PUBLISHES" -> EdgeType.PUBLISHES;
            case "CONSUMES" -> EdgeType.CONSUMES;
            default -> EdgeType.DEPENDS_ON;
        };
    }
}
