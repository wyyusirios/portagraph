package ru.portagraph.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.portagraph.domain.GitRepository;
import ru.portagraph.domain.RunTrigger;
import ru.portagraph.domain.WebhookEvent;
import ru.portagraph.integration.git.GitProviderRegistry;
import ru.portagraph.repository.GitRepositoryRepository;
import ru.portagraph.repository.WebhookEventRepository;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;

/**
 * Синхронизация по webhook (UC-12): проверка подписи, защита от повторов,
 * инкрементальная переиндексация только изменённых файлов.
 */
@Service
public class WebhookService {

    public enum Outcome { ACCEPTED, DUPLICATE, IGNORED_BRANCH, BUSY }

    private final GitRepositoryRepository repositories;
    private final WebhookEventRepository events;
    private final GitProviderRegistry providers;
    private final CredentialCipher cipher;
    private final AnalysisPipeline pipeline;

    public WebhookService(GitRepositoryRepository repositories, WebhookEventRepository events,
                          GitProviderRegistry providers, CredentialCipher cipher, AnalysisPipeline pipeline) {
        this.repositories = repositories;
        this.events = events;
        this.providers = providers;
        this.cipher = cipher;
        this.pipeline = pipeline;
    }

    /** Входящее push-событие, приведённое к общему виду для GitHub и Bitbucket. */
    public record PushEvent(String deliveryId, String branch, String afterSha) { }

    @Transactional
    public Outcome handlePush(Long repositoryId, byte[] rawBody, String signature, PushEvent push) {
        GitRepository repo = repositories.findById(repositoryId)
                .orElseThrow(() -> new NotFoundException("Репозиторий не найден"));
        if (!signatureValid(repo.getWebhookSecret(), rawBody, signature)) {
            throw new SecurityException("Неверная подпись webhook");
        }
        if (events.existsByRepositoryIdAndDeliveryId(repositoryId, push.deliveryId())) {
            return Outcome.DUPLICATE;
        }
        WebhookEvent ev = new WebhookEvent();
        ev.setRepository(repo);
        ev.setDeliveryId(push.deliveryId());
        ev.setEventType("push");
        ev.setBranch(push.branch());
        ev.setCommitSha(push.afterSha());
        events.save(ev);

        if (!repo.getDefaultBranch().equals(push.branch())) {
            ev.setProcessed(true);
            return Outcome.IGNORED_BRANCH; // граф строится по основной ветке
        }
        Set<String> changed = null;
        if (repo.getLastCommitSha() != null) {
            String token = repo.getCredential() == null ? null
                    : cipher.decrypt(repo.getCredential().getEncryptedToken());
            changed = new HashSet<>(providers.get(repo.getProvider())
                    .changedFiles(repo.getUrl(), repo.getLastCommitSha(), push.afterSha(), token));
        }
        try {
            ev.setRun(pipeline.enqueue(repo.getProject().getId(), RunTrigger.WEBHOOK,
                    changed == null ? null : Map.of(repo.getId(), changed)));
            ev.setProcessed(true);
            return Outcome.ACCEPTED;
        } catch (IllegalStateException busy) {
            return Outcome.BUSY; // событие сохранено; планировщик подхватит его позже
        }
    }

    /** Подпись GitHub: {@code sha256=<hex HMAC-SHA256(secret, body)>}. */
    static boolean signatureValid(String secret, byte[] body, String header) {
        if (secret == null || header == null) return false;
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            String expected = "sha256=" + HexFormat.of().formatHex(mac.doFinal(body));
            return MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8),
                    header.trim().getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            return false;
        }
    }
}
