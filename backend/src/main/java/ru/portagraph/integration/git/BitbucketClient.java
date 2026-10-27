package ru.portagraph.integration.git;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import ru.portagraph.domain.GitProvider;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Клиент Bitbucket Cloud REST API 2.0. */
@Component
public class BitbucketClient implements GitProviderClient {

    private static final Pattern URL = Pattern.compile("bitbucket\\.org[/:]([\\w.\\-]+)/([\\w.\\-]+?)(?:\\.git)?/?$");

    private final RestClient http = RestClient.builder()
            .baseUrl("https://api.bitbucket.org/2.0")
            .build();

    @Override
    public GitProvider provider() {
        return GitProvider.BITBUCKET;
    }

    @Override
    public RepositoryInfo verifyAccess(String repositoryUrl, String token) {
        String slug = slug(repositoryUrl);
        JsonNode repo = http.get().uri("/repositories/" + slug)
                .headers(h -> h.setBearerAuth(token))
                .retrieve()
                .onStatus(HttpStatusCode::is4xxClientError, (req, res) -> {
                    throw new RepositoryAccessException("Нет доступа к репозиторию " + slug);
                })
                .body(JsonNode.class);
        return new RepositoryInfo(repo.path("name").asText(),
                repo.path("mainbranch").path("name").asText("main"),
                repo.path("is_private").asBoolean(), true);
    }

    @Override
    public String latestCommit(String repositoryUrl, String branch, String token) {
        JsonNode b = http.get().uri("/repositories/" + slug(repositoryUrl) + "/refs/branches/{branch}", branch)
                .headers(h -> h.setBearerAuth(token)).retrieve().body(JsonNode.class);
        return b.path("target").path("hash").asText();
    }

    @Override
    public List<RemoteFile> listFiles(String repositoryUrl, String commitSha, String token) {
        List<RemoteFile> files = new ArrayList<>();
        String next = "/repositories/" + slug(repositoryUrl) + "/src/" + commitSha + "/?max_depth=20&pagelen=100";
        while (next != null) {
            JsonNode page = http.get().uri(java.net.URI.create(next.startsWith("http") ? next : "https://api.bitbucket.org/2.0" + next)).headers(h -> h.setBearerAuth(token))
                    .retrieve().body(JsonNode.class);
            for (JsonNode n : page.path("values")) {
                if ("commit_file".equals(n.path("type").asText())) {
                    files.add(new RemoteFile(n.path("path").asText(), commitSha, n.path("size").asLong()));
                }
            }
            next = page.hasNonNull("next") ? page.path("next").asText() : null;
        }
        return files;
    }

    @Override
    public String readFile(String repositoryUrl, String commitSha, String path, String token) {
        return http.get().uri("/repositories/" + slug(repositoryUrl) + "/src/{sha}/"
                        + path, commitSha)
                .headers(h -> h.setBearerAuth(token)).retrieve().body(String.class);
    }

    @Override
    public List<String> changedFiles(String repositoryUrl, String fromSha, String toSha, String token) {
        JsonNode diff = http.get().uri("/repositories/" + slug(repositoryUrl) + "/diffstat/{spec}", toSha + ".." + fromSha)
                .headers(h -> h.setBearerAuth(token)).retrieve().body(JsonNode.class);
        List<String> paths = new ArrayList<>();
        for (JsonNode v : diff.path("values")) {
            JsonNode side = v.hasNonNull("new") ? v.path("new") : v.path("old");
            paths.add(side.path("path").asText());
        }
        return paths;
    }

    @Override
    public void registerWebhook(String repositoryUrl, String callbackUrl, String secret, String token) {
        http.post().uri("/repositories/" + slug(repositoryUrl) + "/hooks")
                .headers(h -> h.set(HttpHeaders.AUTHORIZATION, "Bearer " + token))
                .body(Map.of("description", "PortaGraph sync", "url", callbackUrl, "active", true,
                        "secret", secret, "events", List.of("repo:push")))
                .retrieve().toBodilessEntity();
    }

    static String slug(String url) {
        Matcher m = URL.matcher(url.trim());
        if (!m.find()) {
            throw new IllegalArgumentException("Некорректный адрес Bitbucket-репозитория: " + url);
        }
        return m.group(1) + "/" + m.group(2);
    }
}
