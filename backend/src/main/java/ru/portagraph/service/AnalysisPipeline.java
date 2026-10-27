package ru.portagraph.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import ru.portagraph.domain.*;
import ru.portagraph.integration.git.GitProviderRegistry;
import ru.portagraph.repository.AnalysisRunRepository;
import ru.portagraph.repository.GeneratedDocumentRepository;
import ru.portagraph.repository.GitRepositoryRepository;
import ru.portagraph.repository.ProjectRepository;

import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

/**
 * Конвейер анализа проекта. Запускается асинхронно после фиксации транзакции:
 * FETCHING → INDEXING → ANALYZING → BUILDING_GRAPH → COMPLETED (или FAILED).
 * Одновременно для проекта выполняется не более одного анализа.
 */
@Service
public class AnalysisPipeline {

    private static final Logger log = LoggerFactory.getLogger(AnalysisPipeline.class);
    private static final Set<RunStatus> ACTIVE = EnumSet.of(RunStatus.QUEUED, RunStatus.FETCHING,
            RunStatus.INDEXING, RunStatus.ANALYZING, RunStatus.BUILDING_GRAPH);

    private final AnalysisRunRepository runs;
    private final ProjectRepository projects;
    private final GitRepositoryRepository repositories;
    private final GeneratedDocumentRepository documents;
    private final IndexingService indexing;
    private final GraphService graph;
    private final GitProviderRegistry providers;
    private final CredentialCipher cipher;
    private final ApplicationEventPublisher events;

    public AnalysisPipeline(AnalysisRunRepository runs, ProjectRepository projects,
                            GitRepositoryRepository repositories, GeneratedDocumentRepository documents,
                            IndexingService indexing, GraphService graph, GitProviderRegistry providers,
                            CredentialCipher cipher, ApplicationEventPublisher events) {
        this.runs = runs;
        this.projects = projects;
        this.repositories = repositories;
        this.documents = documents;
        this.indexing = indexing;
        this.graph = graph;
        this.providers = providers;
        this.cipher = cipher;
        this.events = events;
    }

    /** Событие «задача поставлена в очередь»; {@code onlyPaths} — для инкрементальной синхронизации. */
    public record RunQueued(Long runId, Map<Long, Set<String>> onlyPaths) { }

    @Transactional
    public AnalysisRun enqueue(Long projectId, RunTrigger trigger) {
        return enqueue(projectId, trigger, null);
    }

    @Transactional
    public AnalysisRun enqueue(Long projectId, RunTrigger trigger, Map<Long, Set<String>> onlyPaths) {
        if (runs.existsByProjectIdAndStatusIn(projectId, ACTIVE)) {
            throw new IllegalStateException("Анализ проекта уже выполняется");
        }
        Project project = projects.findById(projectId).orElseThrow(() -> new NotFoundException("Проект не найден"));
        AnalysisRun run = runs.save(new AnalysisRun(project, trigger));
        events.publishEvent(new RunQueued(run.getId(), onlyPaths));
        return run;
    }

    @Async
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void execute(RunQueued event) {
        AnalysisRun run = runs.findById(event.runId()).orElseThrow();
        Long projectId = run.getProject().getId();
        try {
            run.moveTo(RunStatus.FETCHING);
            var repos = repositories.findByProjectId(projectId);
            Map<Long, String> heads = new java.util.HashMap<>();
            for (GitRepository repo : repos) {
                String token = repo.getCredential() == null ? null
                        : cipher.decrypt(repo.getCredential().getEncryptedToken());
                heads.put(repo.getId(), providers.get(repo.getProvider())
                        .latestCommit(repo.getUrl(), repo.getDefaultBranch(), token));
                repo.setStatus(RepositoryStatus.INDEXING);
            }
            run.setProgress(10);

            run.moveTo(RunStatus.INDEXING);
            int indexed = 0, redacted = 0, i = 0;
            for (GitRepository repo : repos) {
                Set<String> only = event.onlyPaths() == null ? null : event.onlyPaths().get(repo.getId());
                IndexingService.IndexStats s = indexing.indexRepository(repo, heads.get(repo.getId()), only);
                indexed += s.indexed();
                redacted += s.secretsRedacted();
                run.setProgress(10 + 40 * ++i / Math.max(1, repos.size()));
            }

            run.moveTo(RunStatus.ANALYZING);
            var components = graph.analyzeRepositories(run);
            run.setProgress(75);

            run.moveTo(RunStatus.BUILDING_GRAPH);
            int links = graph.linkRepositories(run, components);
            repos.forEach(r -> r.markSynced(heads.get(r.getId())));

            run.getStats().putAll(Map.of("repositories", repos.size(), "filesIndexed", indexed,
                    "secretsRedacted", redacted, "crossRepoLinks", links));
            run.moveTo(RunStatus.COMPLETED);
            documents.markOutdated(projectId, run.getId());
            log.info("Анализ {} проекта {} завершён: {}", run.getId(), projectId, run.getStats());
        } catch (RuntimeException e) {
            log.error("Анализ {} завершился ошибкой", run.getId(), e);
            repositories.findByProjectId(projectId).forEach(r -> r.setStatus(RepositoryStatus.ERROR));
            run.fail(e.getMessage());
        }
    }
}
