package ru.portagraph.integration.git;

import org.springframework.stereotype.Component;
import ru.portagraph.domain.GitProvider;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;

/** Выбор клиента по типу хостинга и определение хостинга по URL. */
@Component
public class GitProviderRegistry {

    private final Map<GitProvider, GitProviderClient> clients = new EnumMap<>(GitProvider.class);

    public GitProviderRegistry(List<GitProviderClient> all) {
        all.forEach(c -> clients.put(c.provider(), c));
    }

    public GitProviderClient get(GitProvider provider) {
        GitProviderClient c = clients.get(provider);
        if (c == null) {
            throw new UnsupportedOperationException("Хостинг " + provider + " пока не поддерживается");
        }
        return c;
    }

    public static GitProvider detect(String url) {
        String u = url.toLowerCase();
        if (u.contains("github.com")) return GitProvider.GITHUB;
        if (u.contains("bitbucket.org")) return GitProvider.BITBUCKET;
        if (u.contains("gitlab")) return GitProvider.GITLAB;
        if (u.contains("gitverse.ru")) return GitProvider.GITVERSE;
        throw new IllegalArgumentException("Не удалось определить Git-хостинг по адресу " + url);
    }
}
