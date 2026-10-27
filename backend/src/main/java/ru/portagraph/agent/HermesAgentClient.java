package ru.portagraph.agent;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.List;
import java.util.Map;

/**
 * Адаптер к агентному ядру Hermes, развёрнутому отдельным сервисом.
 * <p>
 * Каждая операция — отдельная «задача» агента со своим системным промптом и
 * JSON-схемой ответа. Агент сам вызывает LLM API и инструменты (поиск по индексу,
 * чтение файлов), а backend получает только структурированный результат.
 */
@Component
public class HermesAgentClient implements AgentRuntime {

    private final RestClient http;
    private final ObjectMapper json;

    public HermesAgentClient(@Value("${portagraph.agent.url}") String baseUrl,
                             @Value("${portagraph.agent.api-key}") String apiKey,
                             ObjectMapper json) {
        this.json = json;
        this.http = RestClient.builder()
                .baseUrl(baseUrl)
                .defaultHeaders(h -> h.setBearerAuth(apiKey))
                .build();
    }

    @Override
    public RepositoryInsight describeRepository(RepositoryContext context) {
        return run("describe_repository", Map.of("context", context), new TypeReference<>() { });
    }

    @Override
    public List<LinkVerdict> verifyLinks(List<LinkCandidateDto> candidates, Map<String, String> repoSummaries) {
        return run("verify_links", Map.of("candidates", candidates, "repositories", repoSummaries),
                new TypeReference<>() { });
    }

    @Override
    public GroundedAnswer answer(String question, List<ContextSnippet> snippets) {
        return run("answer_question", Map.of("question", question, "snippets", snippets,
                "rules", List.of("Отвечай только по приведённым фрагментам",
                        "Указывай chunkId каждого использованного фрагмента",
                        "Если данных недостаточно — так и скажи")), new TypeReference<>() { });
    }

    @Override
    public String explainImpact(String changeDescription, List<String> affectedComponents) {
        Map<String, String> r = run("explain_impact",
                Map.of("change", changeDescription, "affected", affectedComponents), new TypeReference<>() { });
        return r.getOrDefault("text", "");
    }

    @Override
    public String draftDocument(String documentType, String graphSummary) {
        Map<String, String> r = run("draft_document",
                Map.of("type", documentType, "graph", graphSummary), new TypeReference<>() { });
        return r.getOrDefault("markdown", "");
    }

    private <T> T run(String task, Map<String, Object> input, TypeReference<T> type) {
        Map<?, ?> response = http.post().uri("/v1/tasks/{task}/run", task)
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("input", input, "response_format", "json"))
                .retrieve()
                .body(Map.class);
        if (response == null || !response.containsKey("output")) {
            throw new AgentException("Агент не вернул результат для задачи " + task);
        }
        return json.convertValue(response.get("output"), type);
    }
}
