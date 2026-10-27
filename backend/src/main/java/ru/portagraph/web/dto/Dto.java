package ru.portagraph.web.dto;

import jakarta.validation.constraints.*;
import ru.portagraph.core.graph.ArchitectureGraph;
import ru.portagraph.domain.*;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/** DTO REST API. Сущности JPA наружу не отдаются. */
public final class Dto {

    private Dto() { }

    // ---- аутентификация
    public record RegisterRequest(@Email @NotBlank String email,
                                  @NotBlank @Size(min = 8, max = 100) String password,
                                  @NotBlank @Size(max = 150) String fullName) { }

    public record LoginRequest(@Email @NotBlank String email, @NotBlank String password) { }

    public record TokenResponse(String accessToken, long expiresInSeconds) { }

    // ---- проекты
    public record CreateProjectRequest(@NotBlank @Size(max = 120) String name, @Size(max = 2000) String description) { }

    public record ProjectView(Long id, String name, String description, ProjectStatus status,
                              int repositoryCount, Instant createdAt) {
        public static ProjectView of(Project p) {
            return new ProjectView(p.getId(), p.getName(), p.getDescription(), p.getStatus(),
                    p.getRepositories().size(), p.getCreatedAt());
        }
    }

    public record AddMemberRequest(@Email @NotBlank String email, @NotNull ProjectRole role) { }

    // ---- репозитории
    public record ConnectRepositoriesRequest(@NotEmpty @Size(max = 50) List<@NotBlank String> urls,
                                             @NotBlank String accessToken) { }

    public record RepositoryView(Long id, String name, String url, GitProvider provider, RepositoryRole role,
                                 double roleConfidence, String purpose, RepositoryStatus status,
                                 String lastCommitSha, Instant lastSyncedAt) {
        public static RepositoryView of(GitRepository r) {
            return new RepositoryView(r.getId(), r.getName(), r.getUrl(), r.getProvider(), r.getDetectedRole(),
                    r.getRoleConfidence(), r.getPurposeSummary(), r.getStatus(), r.getLastCommitSha(),
                    r.getLastSyncedAt());
        }
    }

    // ---- анализ
    public record RunView(Long id, RunTrigger trigger, RunStatus status, int progress,
                          Instant startedAt, Instant finishedAt, String error, Map<String, Object> stats) {
        public static RunView of(AnalysisRun r) {
            return new RunView(r.getId(), r.getTrigger(), r.getStatus(), r.getProgress(), r.getStartedAt(),
                    r.getFinishedAt(), r.getErrorMessage(), r.getStats());
        }
    }

    // ---- граф (формат, удобный для React Flow)
    public record GraphView(List<NodeView> nodes, List<EdgeView> edges) {
        public static GraphView of(ArchitectureGraph g) {
            List<NodeView> ns = g.nodes().stream()
                    .map(n -> new NodeView(String.valueOf(n.id()), n.type(), n.name(),
                            n.parentId() == null ? null : String.valueOf(n.parentId()))).toList();
            List<EdgeView> es = g.nodes().stream().flatMap(n -> g.dependenciesOf(n.id()).stream())
                    .map(e -> new EdgeView(e.from() + "-" + e.to() + "-" + e.type(), String.valueOf(e.from()),
                            String.valueOf(e.to()), e.type(), e.confidence())).toList();
            return new GraphView(ns, es);
        }
    }

    public record NodeView(String id, String type, String label, String parentId) { }

    public record EdgeView(String id, String source, String target, String type, double confidence) { }

    public record VerifyNodeRequest(@Size(max = 2000) String correctedDescription) { }

    // ---- AI-вопросы
    public record AskRequest(Long sessionId, @NotBlank @Size(max = 4000) String question) { }

    public record CitationView(Long fileId, String path, int startLine, int endLine) { }

    public record AnswerView(Long sessionId, Long messageId, String text, List<CitationView> citations) {
        public static AnswerView of(ChatMessage m) {
            return new AnswerView(m.getSession().getId(), m.getId(), m.getContent(), m.getCitations().stream()
                    .map(c -> new CitationView(c.getSourceFile().getId(), c.getSourceFile().getPath(),
                            c.getStartLine(), c.getEndLine())).toList());
        }
    }

    // ---- impact analysis
    public record ImpactRequest(@NotBlank @Size(max = 2000) String changeDescription,
                                @NotEmpty List<Long> nodeIds, @Min(1) @Max(6) Integer depth) { }

    public record ImpactView(Long id, String changeDescription, RiskLevel risk, int depth,
                             List<Map<String, Object>> affected, String recommendation, Instant createdAt) {
        public static ImpactView of(ImpactReport r) {
            return new ImpactView(r.getId(), r.getChangeDescription(), r.getRiskLevel(), r.getMaxDepth(),
                    r.getAffected(), r.getRecommendation(), r.getCreatedAt());
        }
    }

    // ---- документы
    public record GenerateDocumentRequest(@NotNull DocumentType type) { }

    public record DocumentView(Long id, DocumentType type, String title, DocumentStatus status,
                               String contentMd, Instant createdAt, Instant approvedAt) {
        public static DocumentView of(GeneratedDocument d) {
            return new DocumentView(d.getId(), d.getType(), d.getTitle(), d.getStatus(), d.getContentMd(),
                    d.getCreatedAt(), d.getApprovedAt());
        }
    }

    public record ErrorView(int status, String error, String message) { }
}
