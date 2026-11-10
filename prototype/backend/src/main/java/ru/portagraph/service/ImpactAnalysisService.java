package ru.portagraph.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.portagraph.agent.AgentRuntime;
import ru.portagraph.core.graph.ArchitectureGraph;
import ru.portagraph.core.impact.ImpactAnalyzer;
import ru.portagraph.domain.ImpactReport;
import ru.portagraph.domain.RiskLevel;
import ru.portagraph.repository.ImpactReportRepository;
import ru.portagraph.repository.ProjectRepository;
import ru.portagraph.repository.UserRepository;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Impact analysis предполагаемого изменения (UC-10). */
@Service
public class ImpactAnalysisService {

    static final int DEFAULT_DEPTH = 3;
    static final int MAX_DEPTH = 6;

    private final GraphService graphs;
    private final AgentRuntime agent;
    private final ImpactReportRepository reports;
    private final ProjectRepository projects;
    private final UserRepository users;
    private final AccessGuard guard;

    public ImpactAnalysisService(GraphService graphs, AgentRuntime agent, ImpactReportRepository reports,
                                 ProjectRepository projects, UserRepository users, AccessGuard guard) {
        this.graphs = graphs;
        this.agent = agent;
        this.reports = reports;
        this.projects = projects;
        this.users = users;
        this.guard = guard;
    }

    @Transactional
    public ImpactReport analyze(Long projectId, Long userId, String changeDescription,
                                List<Long> changedNodeIds, Integer depth) {
        guard.requireMember(projectId, userId);
        int d = depth == null ? DEFAULT_DEPTH : Math.min(MAX_DEPTH, Math.max(1, depth));

        ArchitectureGraph graph = graphs.loadGraph(projectId);
        ImpactAnalyzer.ImpactResult result = new ImpactAnalyzer(graph).analyze(changedNodeIds, d);

        List<Map<String, Object>> affected = result.affected().stream().map(a -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("nodeId", a.node().id());
            m.put("name", a.node().name());
            m.put("type", a.node().type());
            m.put("distance", a.distance());
            m.put("score", Math.round(a.score() * 1000) / 1000.0);
            m.put("path", a.path());
            return m;
        }).toList();

        ImpactReport report = new ImpactReport();
        report.setProject(projects.getReferenceById(projectId));
        report.setAuthor(users.getReferenceById(userId));
        report.setChangeDescription(changeDescription);
        report.setChangedNodeIds(changedNodeIds);
        report.setMaxDepth(d);
        report.setAffected(affected);
        report.setRiskLevel(RiskLevel.valueOf(result.risk().name()));
        report.setRecommendation(agent.explainImpact(changeDescription,
                result.affected().stream().map(a -> a.node().type() + " " + a.node().name()).toList()));
        return reports.save(report);
    }

    @Transactional(readOnly = true)
    public List<ImpactReport> history(Long projectId, Long userId) {
        guard.requireMember(projectId, userId);
        return reports.findByProjectIdOrderByCreatedAtDesc(projectId);
    }
}
