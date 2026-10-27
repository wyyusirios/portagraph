package ru.portagraph.integration.git;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import ru.portagraph.domain.GitProvider;

import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Клиент GitHub REST API v3. */
@Component
public class GitHubClient implements GitProviderClient {

    private static final Pattern URL = Pattern.compile("github\\.com[/:]([\\w.\\-]+)/([\\w.\\-]+?)(?:\\.git)?/?$");

    private final RestClient http = RestClient.builder()
            .baseUrl("https://api.github.com")
            .defaultHeader(HttpHeaders.ACCEPT, "application/vnd.github+json")
            .defaultHeader("X-GitHub-Api-Version", "2022-11-28")
            .build();

    @Override
    public GitProvider provider() {
        return GitProvider.GITHUB;
    }

    @Override
    public RepositoryInfo verifyAccess(String repositoryUrl, String token) {
        String slug = slug(repositoryUrl);
        JsonNode repo = http.get().uri("/repos/" + slug)
                .headers(h -> auth(h, token))
                .retrieve()
                .onStatus(HttpStatusCode::is4xxClientError, (req, res) -> {
                    throw new RepositoryAccessException("Нет доступа к репозиторию " + slug
                            + " (HTTP " + res.getStatusCode().value() + ")");
                })
                .body(JsonNode.class);
        boolean canRead = repo.path("permissions").path("pull").asBoolean(true);
        return new RepositoryInfo(repo.path("name").asText(), repo.path("default_branch").asText("main"),
                repo.path("private").asBoolean(), canRead);
    }

    @Override
    public String latestCommit(String repositoryUrl, String branch, String token) {
        JsonNode b = http.get().uri("/repos/" + slug(repositoryUrl) + "/branches/{branch}", branch)
                .headers(h -> auth(h, token)).retrieve().body(JsonNode.class);
        return b.path("commit").path("sha").asText();
    }

    @Override
    public List<RemoteFile> listFiles(String repositoryUrl, String commitSha, String token) {
        JsonNode tree = http.get().uri("/repos/" + slug(repositoryUrl) + "/git/trees/{sha}?recursive=1", commitSha)
                .headers(h -> auth(h, token)).retrieve().body(JsonNode.class);
        List<RemoteFile> files = new ArrayList<>();
        for (JsonNode n : tree.path("tree")) {
            if ("blob".equals(n.path("type").asText())) {
                files.add(new RemoteFile(n.path("path").asText(), n.path("sha").asText(), n.path("size").asLong()));
            }
        }
        return files;
    }

    @Override
    public String readFile(String repositoryUrl, String commitSha, String path, String token) {
        JsonNode f = http.get().uri("/repos/" + slug(repositoryUrl) + "/contents/" + path + "?ref={sha}", commitSha)
                .headers(h -> auth(h, token)).retrieve().body(JsonNode.class);
        String b64 = f.path("content").asText().replace("\n", "");
        return new String(Base64.getDecoder().decode(b64));
    }

    @Override
    public List<String> changedFiles(String repositoryUrl, String fromSha, String toSha, String token) {
        JsonNode cmp = http.get().uri("/repos/" + slug(repositoryUrl) + "/compare/{from}...{to}", fromSha, toSha)
                .headers(h -> auth(h, token)).retrieve().body(JsonNode.class);
        List<String> paths = new ArrayList<>();
        cmp.path("files").forEach(f -> paths.add(f.path("filename").asText()));
        return paths;
    }

    @Override
    public void registerWebhook(String repositoryUrl, String callbackUrl, String secret, String token) {
        http.post().uri("/repos/" + slug(repositoryUrl) + "/hooks")
                .headers(h -> auth(h, token))
                .body(Map.of("name", "web", "active", true, "events", List.of("push"),
                        "config", Map.of("url", callbackUrl, "content_type", "json", "secret", secret)))
                .retrieve().toBodilessEntity();
    }

    static String slug(String url) {
        Matcher m = URL.matcher(url.trim());
        if (!m.find()) {
            throw new IllegalArgumentException("Некорректный адрес GitHub-репозитория: " + url);
        }
        return m.group(1) + "/" + m.group(2);
    }

    private static void auth(HttpHeaders h, String token) {
        if (token != null && !token.isBlank()) {
            h.setBearerAuth(token);
        }
    }
}
