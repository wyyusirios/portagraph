package ru.portagraph.core;

import org.junit.jupiter.api.Test;
import ru.portagraph.core.analysis.DependencyExtractor;
import ru.portagraph.core.analysis.DependencyExtractor.LinkType;
import ru.portagraph.core.analysis.RepositoryRoleClassifier;
import ru.portagraph.core.analysis.RepositoryRoleClassifier.Role;
import ru.portagraph.core.analysis.SymbolExtractor;
import ru.portagraph.core.indexing.CodeChunker;

import java.util.Collections;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class IndexingCoreTest {

    @Test
    void chunkerUsesOverlappingWindows() {
        String text = String.join("\n", Collections.nCopies(25, "line"));
        var chunks = new CodeChunker(10, 2).chunk(text, null);
        assertEquals(3, chunks.size());
        assertEquals(9, chunks.get(1).startLine());
        assertEquals(25, chunks.get(2).endLine());
    }

    @Test
    void classifierDetectsServiceAndFrontend() {
        var c = new RepositoryRoleClassifier();
        assertEquals(Role.SERVICE, c.classify(List.of("Dockerfile",
                "src/main/java/a/OrderApplication.java", "src/main/java/a/web/OrderController.java")).role());
        assertEquals(Role.FRONTEND, c.classify(List.of("package.json", "next.config.js", "app/page.tsx")).role());
        assertEquals(Role.DOCUMENTATION, c.classify(List.of("README.md", "docs/a.md", "docs/b.md")).role());
    }

    @Test
    void extractorFindsHttpCallsTopicsAndArtifacts() {
        var ex = new DependencyExtractor(Set.of("auth-service"), Set.of("common-dto"));
        var links = ex.extract("src/Client.java", """
                var url = "http://auth-service:8080/api/v1/users";
                kafka.send("orders.created", event);
                @KafkaListener(topics = "payments.done")
                """);
        assertEquals(List.of(LinkType.CALLS_HTTP, LinkType.PUBLISHES, LinkType.CONSUMES),
                links.stream().map(DependencyExtractor.LinkCandidate::type).toList());
        assertEquals(1, ex.extract("pom.xml", "<artifactId>common-dto</artifactId>\n<artifactId>spring-web</artifactId>").size());
    }

    @Test
    void symbolExtractorFindsClassBoundaries() {
        String java = "public class OrderService {\n  String s = \"}\";\n  void a() { }\n}\n";
        var symbols = new SymbolExtractor().extract("java", java);
        assertEquals("OrderService", symbols.get(0).name());
        assertEquals(4, symbols.get(0).endLine());
    }
}
