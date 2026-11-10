package ru.portagraph.core.analysis;

import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Поиск межрепозиторных связей в коде и конфигурации.
 * <p>
 * Находит кандидатов в рёбра графа: HTTP-вызовы других сервисов по имени хоста,
 * публикацию и чтение топиков очередей, зависимости на артефакты других репозиториев.
 * Кандидаты затем проверяет агентное ядро; итоговая уверенность хранится в ребре.
 */
public class DependencyExtractor {

    public enum LinkType { CALLS_HTTP, PUBLISHES, CONSUMES, DEPENDS_ON_ARTIFACT }

    /** Кандидат связи: из текущего репозитория к цели {@code target}. */
    public record LinkCandidate(LinkType type, String target, String evidence, int line) { }

    private static final Pattern HTTP_HOST = Pattern.compile(
            "https?://([a-z][a-z0-9\\-]{1,62})(?::\\d{2,5})?(/[\\w\\-/{}.]*)?");
    private static final Pattern KAFKA_SEND = Pattern.compile(
            "(?:send|publish|produce)\\s*\\(\\s*\"([\\w.\\-]+)\"");
    private static final Pattern KAFKA_LISTEN = Pattern.compile(
            "(?:@KafkaListener\\s*\\(\\s*topics\\s*=\\s*\\{?\\s*\"|subscribe\\s*\\(\\s*\")([\\w.\\-]+)\"");
    private static final Pattern MAVEN_ARTIFACT = Pattern.compile(
            "<artifactId>([\\w.\\-]+)</artifactId>");
    private static final Pattern NPM_DEP = Pattern.compile(
            "\"(@[\\w\\-]+/[\\w.\\-]+|[\\w.\\-]+)\"\\s*:\\s*\"(?:workspace:|file:|\\^|~)?[\\w.\\-*]+\"");

    /** Имена сервисов и артефактов, известные по другим репозиториям проекта. */
    private final Set<String> knownServices;
    private final Set<String> knownArtifacts;

    public DependencyExtractor(Set<String> knownServices, Set<String> knownArtifacts) {
        this.knownServices = lower(knownServices);
        this.knownArtifacts = lower(knownArtifacts);
    }

    public List<LinkCandidate> extract(String path, String content) {
        List<LinkCandidate> out = new ArrayList<>();
        String[] lines = content.split("\n", -1);
        boolean pom = path.endsWith("pom.xml");
        boolean packageJson = path.endsWith("package.json");

        for (int i = 0; i < lines.length; i++) {
            String line = lines[i];
            int no = i + 1;

            Matcher h = HTTP_HOST.matcher(line);
            while (h.find()) {
                String host = h.group(1).toLowerCase(Locale.ROOT);
                if (knownServices.contains(host)) {
                    out.add(new LinkCandidate(LinkType.CALLS_HTTP, host, line.strip(), no));
                }
            }
            Matcher s = KAFKA_SEND.matcher(line);
            while (s.find()) out.add(new LinkCandidate(LinkType.PUBLISHES, s.group(1), line.strip(), no));
            Matcher l = KAFKA_LISTEN.matcher(line);
            while (l.find()) out.add(new LinkCandidate(LinkType.CONSUMES, l.group(1), line.strip(), no));

            if (pom) {
                Matcher a = MAVEN_ARTIFACT.matcher(line);
                while (a.find()) addArtifact(out, a.group(1), line, no);
            }
            if (packageJson) {
                Matcher d = NPM_DEP.matcher(line);
                while (d.find()) addArtifact(out, d.group(1), line, no);
            }
        }
        return out;
    }

    private void addArtifact(List<LinkCandidate> out, String artifact, String line, int no) {
        if (knownArtifacts.contains(artifact.toLowerCase(Locale.ROOT))) {
            out.add(new LinkCandidate(LinkType.DEPENDS_ON_ARTIFACT, artifact, line.strip(), no));
        }
    }

    private static Set<String> lower(Set<String> src) {
        Set<String> s = new HashSet<>();
        if (src != null) src.forEach(v -> s.add(v.toLowerCase(Locale.ROOT)));
        return Collections.unmodifiableSet(s);
    }
}
