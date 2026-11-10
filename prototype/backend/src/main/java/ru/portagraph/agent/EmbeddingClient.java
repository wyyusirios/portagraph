package ru.portagraph.agent;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.List;
import java.util.Map;

/**
 * Получение векторных представлений текста через LLM API
 * (OpenAI-совместимый эндпоинт {@code /v1/embeddings}).
 */
@Component
public class EmbeddingClient {

    private final RestClient http;
    private final String model;

    public EmbeddingClient(@Value("${portagraph.llm.url}") String baseUrl,
                           @Value("${portagraph.llm.api-key}") String apiKey,
                           @Value("${portagraph.llm.embedding-model}") String model) {
        this.model = model;
        this.http = RestClient.builder().baseUrl(baseUrl)
                .defaultHeaders(h -> h.setBearerAuth(apiKey)).build();
    }

    @SuppressWarnings("unchecked")
    public List<float[]> embed(List<String> texts) {
        Map<String, Object> res = http.post().uri("/v1/embeddings")
                .body(Map.of("model", model, "input", texts))
                .retrieve().body(Map.class);
        List<Map<String, Object>> data = (List<Map<String, Object>>) res.get("data");
        return data.stream().map(d -> toArray((List<Number>) d.get("embedding"))).toList();
    }

    public float[] embed(String text) {
        return embed(List.of(text)).get(0);
    }

    /** Формат литерала pgvector: {@code [0.1,0.2,...]}. */
    public static String toPgVector(float[] v) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < v.length; i++) {
            if (i > 0) sb.append(',');
            sb.append(v[i]);
        }
        return sb.append(']').toString();
    }

    private static float[] toArray(List<Number> list) {
        float[] a = new float[list.size()];
        for (int i = 0; i < a.length; i++) a[i] = list.get(i).floatValue();
        return a;
    }
}
