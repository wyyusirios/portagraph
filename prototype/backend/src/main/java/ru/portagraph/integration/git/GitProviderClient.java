package ru.portagraph.integration.git;

import ru.portagraph.domain.GitProvider;

import java.util.List;

/**
 * Клиент Git-хостинга. Реализации: {@link GitHubClient}, {@link BitbucketClient}.
 * Новые хостинги подключаются добавлением реализации (модульное расширение).
 */
public interface GitProviderClient {

    GitProvider provider();

    /** Проверяет токен и права чтения; возвращает метаданные репозитория. */
    RepositoryInfo verifyAccess(String repositoryUrl, String token);

    /** SHA последнего коммита ветки. */
    String latestCommit(String repositoryUrl, String branch, String token);

    /** Список файлов ветки на указанном коммите. */
    List<RemoteFile> listFiles(String repositoryUrl, String commitSha, String token);

    /** Содержимое файла. */
    String readFile(String repositoryUrl, String commitSha, String path, String token);

    /** Пути файлов, изменённых между двумя коммитами (для инкрементальной синхронизации). */
    List<String> changedFiles(String repositoryUrl, String fromSha, String toSha, String token);

    /** Регистрирует webhook на push-события. */
    void registerWebhook(String repositoryUrl, String callbackUrl, String secret, String token);

    record RepositoryInfo(String name, String defaultBranch, boolean privateRepo, boolean canRead) { }

    record RemoteFile(String path, String sha, long size) { }
}
