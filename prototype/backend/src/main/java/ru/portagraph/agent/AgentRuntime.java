package ru.portagraph.agent;

import java.util.List;
import java.util.Map;

/**
 * Абстракция агентного ядра. Основная реализация — {@link HermesAgentClient}.
 * Агент получает очищенные от секретов материалы репозитория и возвращает
 * структурированные выводы, которые затем превращаются в узлы и рёбра графа.
 */
public interface AgentRuntime {

    /** Определить назначение репозитория и его ключевые модули по README, структуре и точкам входа. */
    RepositoryInsight describeRepository(RepositoryContext context);

    /** Проверить кандидатов в межрепозиторные связи и оценить уверенность. */
    List<LinkVerdict> verifyLinks(List<LinkCandidateDto> candidates, Map<String, String> repoSummaries);

    /** Ответ на вопрос по найденным фрагментам кода (RAG). */
    GroundedAnswer answer(String question, List<ContextSnippet> snippets);

    /** Пояснение к результату impact analysis: что проверить, кого предупредить. */
    String explainImpact(String changeDescription, List<String> affectedComponents);

    /** Черновик документа (архитектурное описание или онбординг) по графу. */
    String draftDocument(String documentType, String graphSummary);

    record RepositoryContext(String repositoryName, String readme, List<String> filePaths,
                             List<String> entryPoints, String apiSpec) { }

    record ModuleInsight(String name, String path, String purpose) { }

    record RepositoryInsight(String role, String purpose, double confidence, List<ModuleInsight> modules) { }

    record LinkCandidateDto(String fromRepository, String type, String target, String evidence) { }

    record LinkVerdict(String fromRepository, String toRepository, String type, double confidence,
                       String rationale) { }

    record ContextSnippet(long chunkId, String path, int startLine, int endLine, String content) { }

    /** Ответ и номера фрагментов, на которые он опирается. */
    record GroundedAnswer(String text, List<Long> usedChunkIds, double confidence) { }
}
