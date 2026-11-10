package ru.portagraph.core;

import org.junit.jupiter.api.Test;
import ru.portagraph.core.security.SecretScanner;

import static org.junit.jupiter.api.Assertions.*;

class SecretScannerTest {

    private final SecretScanner scanner = new SecretScanner();

    @Test
    void redactsPasswordsTokensAndConnectionStrings() {
        String src = """
                db.url=postgres://app:SuperPass1@db:5432/orders
                api_key = "abcdef123456"
                token: ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
                """;
        var r = scanner.scan(src);
        assertEquals(3, r.findings().size());
        assertFalse(r.sanitized().contains("SuperPass1"));
        assertFalse(r.sanitized().contains("abcdef123456"));
        assertTrue(r.sanitized().contains("[REDACTED:GITHUB_TOKEN]"));
    }

    @Test
    void keepsOrdinaryCodeUntouched() {
        String code = "int port = 8080;\nString name = user.getName();";
        var r = scanner.scan(code);
        assertFalse(r.hasSecrets());
        assertEquals(code, r.sanitized());
    }

    @Test
    void skipsSecretFiles() {
        assertTrue(scanner.isSecretFile("config/.env"));
        assertTrue(scanner.isSecretFile("certs/server.pem"));
        assertFalse(scanner.isSecretFile("src/main/java/Env.java"));
    }
}
