package ru.portagraph.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.portagraph.domain.*;
import ru.portagraph.integration.git.GitProviderClient;
import ru.portagraph.integration.git.GitProviderRegistry;
import ru.portagraph.integration.git.RepositoryAccessException;
import ru.portagraph.repository.GitRepositoryRepository;
import ru.portagraph.repository.RepoCredentialRepository;

import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;

/**
 * Подключение набора репозиториев к проекту (UC-03).
 * Роли репозиториев пользователь не указывает — их определит анализ.
 */
@Service
public class RepositoryConnectionService {

    private final GitRepositoryRepository repositories;
    private final RepoCredentialRepository credentials;
    private final GitProviderRegistry providers;
    private final CredentialCipher cipher;
    private final ProjectService projects;
    private final AccessGuard guard;
    private final AnalysisPipeline pipeline;
    private final String publicUrl;
    private final SecureRandom random = new SecureRandom();

    public RepositoryConnectionService(GitRepositoryRepository repositories, RepoCredentialRepository credentials,
                                       GitProviderRegistry providers, CredentialCipher cipher,
                                       ProjectService projects, AccessGuard guard, AnalysisPipeline pipeline,
                                       @Value("${portagraph.public-url}") String publicUrl) {
        this.repositories = repositories;
        this.credentials = credentials;
        this.providers = providers;
        this.cipher = cipher;
        this.projects = projects;
        this.guard = guard;
        this.pipeline = pipeline;
        this.publicUrl = publicUrl;
    }

    /** Результат подключения одного репозитория. */
    public record ConnectResult(String url, boolean connected, String message, Long repositoryId) { }

    /**
     * Проверяет доступ к каждому адресу, сохраняет зашифрованный токен,
     * регистрирует webhook и запускает первичный анализ проекта.
     */
    @Transactional
    public List<ConnectResult> connect(Long projectId, Long userId, List<String> urls, String token) {
        guard.requireOwner(projectId, userId);
        if (urls == null || urls.isEmpty()) {
            throw new IllegalArgumentException("Укажите хотя бы один репозиторий");
        }
        Project project = projects.get(projectId, userId);
        List<ConnectResult> results = new ArrayList<>();
        boolean anyConnected = false;

        for (String raw : urls.stream().map(String::strip).distinct().toList()) {
            try {
                if (repositories.existsByProjectIdAndUrl(projectId, raw)) {
                    results.add(new ConnectResult(raw, false, "Репозиторий уже подключён", null));
                    continue;
                }
                GitProvider provider = GitProviderRegistry.detect(raw);
                GitProviderClient client = providers.get(provider);
                GitProviderClient.RepositoryInfo info = client.verifyAccess(raw, token);
                if (!info.canRead()) {
                    throw new RepositoryAccessException("Токен не даёт прав на чтение");
                }
                RepoCredential cred = new RepoCredential();
                cred.setProject(project);
                cred.setProvider(provider);
                cred.setEncryptedToken(cipher.encrypt(token));
                cred.setScopes("read");
                credentials.save(cred);

                GitRepository repo = new GitRepository(provider, raw, info.name(), info.defaultBranch());
                repo.setCredential(cred);
                repo.setWebhookSecret(HexFormat.of().formatHex(randomBytes(32)));
                project.addRepository(repo);
                repositories.save(repo);

                try {
                    client.registerWebhook(raw, publicUrl + "/api/webhooks/" + provider.name().toLowerCase()
                            + "/" + repo.getId(), repo.getWebhookSecret(), token);
                } catch (RuntimeException e) {
                    // без webhook проект работает, синхронизация будет по расписанию
                }
                results.add(new ConnectResult(raw, true, "Подключён", repo.getId()));
                anyConnected = true;
            } catch (RepositoryAccessException | IllegalArgumentException | UnsupportedOperationException e) {
                results.add(new ConnectResult(raw, false, e.getMessage(), null));
            }
        }
        if (anyConnected) {
            pipeline.enqueue(projectId, RunTrigger.MANUAL);
        }
        return results;
    }

    @Transactional(readOnly = true)
    public List<GitRepository> list(Long projectId, Long userId) {
        guard.requireMember(projectId, userId);
        return repositories.findByProjectId(projectId);
    }

    @Transactional
    public void disconnect(Long projectId, Long userId, Long repositoryId) {
        guard.requireOwner(projectId, userId);
        GitRepository repo = repositories.findById(repositoryId)
                .filter(r -> r.getProject().getId().equals(projectId))
                .orElseThrow(() -> new NotFoundException("Репозиторий не найден"));
        repositories.delete(repo);
    }

    private byte[] randomBytes(int n) {
        byte[] b = new byte[n];
        random.nextBytes(b);
        return b;
    }
}
