package ru.portagraph.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.portagraph.agent.EmbeddingClient;
import ru.portagraph.core.indexing.CodeChunker;
import ru.portagraph.core.security.SecretScanner;
import ru.portagraph.domain.*;
import ru.portagraph.integration.git.GitProviderClient;
import ru.portagraph.integration.git.GitProviderClient.RemoteFile;
import ru.portagraph.integration.git.GitProviderRegistry;
import ru.portagraph.repository.CodeChunkRepository;
import ru.portagraph.repository.SourceFileRepository;

import java.util.*;

/**
 * Индексация исходного кода и документации (UC-04).
 * <p>
 * Для каждого файла: фильтр по типу → маскирование секретов → сохранение очищенной
 * копии в S3 → нарезка на фрагменты → embeddings → запись в pgvector. Файлы, чей SHA
 * не изменился с прошлой индексации, пропускаются.
 */
@Service
public class IndexingService {

    /** Файлы больше этого размера не индексируются (сгенерированный код, дампы). */
    static final long MAX_FILE_BYTES = 512 * 1024;
    private static final int EMBED_BATCH = 64;

    private static final Map<String, String> LANGUAGES = Map.ofEntries(
            Map.entry("java", "java"), Map.entry("kt", "kotlin"), Map.entry("ts", "typescript"),
            Map.entry("tsx", "typescript"), Map.entry("js", "javascript"), Map.entry("py", "python"),
            Map.entry("go", "go"), Map.entry("cs", "csharp"), Map.entry("sql", "sql"));

    private final GitProviderRegistry providers;
    private final CredentialCipher cipher;
    private final SourceFileRepository files;
    private final CodeChunkRepository chunks;
    private final EmbeddingClient embeddings;
    private final ArtifactStorage storage;
    private final SecretScanner secrets = new SecretScanner();
    private final CodeChunker chunker = new CodeChunker(60, 10);

    public IndexingService(GitProviderRegistry providers, CredentialCipher cipher, SourceFileRepository files,
                           CodeChunkRepository chunks, EmbeddingClient embeddings, ArtifactStorage storage) {
        this.providers = providers;
        this.cipher = cipher;
        this.files = files;
        this.chunks = chunks;
        this.embeddings = embeddings;
        this.storage = storage;
    }

    /** Статистика индексации одного репозитория. */
    public record IndexStats(int indexed, int skipped, int secretsRedacted) { }

    /**
     * @param onlyPaths если не {@code null} — индексируются только эти пути (инкрементальная синхронизация)
     */
    @Transactional
    public IndexStats indexRepository(GitRepository repo, String commitSha, Set<String> onlyPaths) {
        GitProviderClient client = providers.get(repo.getProvider());
        String token = repo.getCredential() == null ? null
                : cipher.decrypt(repo.getCredential().getEncryptedToken());
        int indexed = 0, skipped = 0, redacted = 0;

        for (RemoteFile rf : client.listFiles(repo.getUrl(), commitSha, token)) {
            if (onlyPaths != null && !onlyPaths.contains(rf.path())) continue;
            Optional<FileKind> kind = classify(rf.path());
            if (kind.isEmpty() || rf.size() > MAX_FILE_BYTES || secrets.isSecretFile(rf.path())) {
                skipped++;
                continue;
            }
            Optional<SourceFile> existing = files.findByRepositoryIdAndPath(repo.getId(), rf.path());
            if (existing.isPresent() && existing.get().getContentSha().equals(rf.sha())) {
                skipped++;
                continue;
            }
            String raw = client.readFile(repo.getUrl(), commitSha, rf.path(), token);
            SecretScanner.ScanResult scan = secrets.scan(raw);
            redacted += scan.findings().size();

            SourceFile sf = existing.orElseGet(() -> new SourceFile(repo, rf.path(), language(rf.path()),
                    kind.get(), rf.sha(), rf.size()));
            sf.setContentSha(rf.sha());
            sf.setSizeBytes(rf.size());
            sf.setStorageKey(storage.putText(
                    ArtifactStorage.fileKey(repo.getProject().getId(), repo.getId(), rf.path()), scan.sanitized()));
            files.save(sf);
            existing.ifPresent(f -> chunks.deleteBySourceFileId(f.getId()));
            storeChunks(sf, scan.sanitized());
            indexed++;
        }
        return new IndexStats(indexed, skipped, redacted);
    }

    private void storeChunks(SourceFile sf, String content) {
        List<CodeChunker.Chunk> parts = chunker.chunk(content, null);
        for (int from = 0; from < parts.size(); from += EMBED_BATCH) {
            List<CodeChunker.Chunk> batch = parts.subList(from, Math.min(parts.size(), from + EMBED_BATCH));
            List<float[]> vectors = embeddings.embed(batch.stream()
                    .map(c -> sf.getPath() + "\n" + c.content()).toList());
            for (int i = 0; i < batch.size(); i++) {
                CodeChunker.Chunk c = batch.get(i);
                CodeChunk entity = new CodeChunk(sf, c.startLine(), c.endLine(), c.symbol(), c.content());
                entity.setEmbedding(vectors.get(i));
                chunks.save(entity);
            }
        }
    }

    static Optional<FileKind> classify(String path) {
        String p = path.toLowerCase(Locale.ROOT);
        String name = p.substring(p.lastIndexOf('/') + 1);
        if (p.contains("node_modules/") || p.contains("/target/") || p.contains("/build/")
                || p.contains("/dist/") || p.startsWith(".git/")) return Optional.empty();
        if (name.startsWith("readme")) return Optional.of(FileKind.README);
        if (name.startsWith("openapi") || name.startsWith("swagger") || name.endsWith(".proto")
                || name.endsWith(".graphql")) return Optional.of(FileKind.API_SPEC);
        if (name.endsWith(".md") || name.endsWith(".adoc")) return Optional.of(FileKind.DOCUMENTATION);
        if (name.equals("pom.xml") || name.equals("package.json") || name.equals("build.gradle")
                || name.equals("build.gradle.kts") || name.equals("go.mod")) return Optional.of(FileKind.BUILD_SCRIPT);
        if (name.endsWith(".yml") || name.endsWith(".yaml") || name.endsWith(".properties")
                || name.equals("dockerfile")) return Optional.of(FileKind.CONFIG);
        String ext = name.contains(".") ? name.substring(name.lastIndexOf('.') + 1) : "";
        return LANGUAGES.containsKey(ext) ? Optional.of(FileKind.CODE) : Optional.empty();
    }

    static String language(String path) {
        String ext = path.contains(".") ? path.substring(path.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT) : "";
        return LANGUAGES.getOrDefault(ext, null);
    }
}
