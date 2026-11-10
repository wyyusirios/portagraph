package ru.portagraph.core.security;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Поиск и маскирование секретов перед индексацией.
 * <p>
 * Требование паспорта проекта: секреты не должны попадать в индекс и в запросы к LLM.
 * Сканер находит типовые токены и ключи и заменяет их маркером {@code [REDACTED:тип]}.
 */
public class SecretScanner {

    /** Найденный секрет (без самого значения — его нельзя логировать). */
    public record Finding(String type, int line) { }

    /** Результат маскирования. */
    public record ScanResult(String sanitized, List<Finding> findings) {
        public boolean hasSecrets() {
            return !findings.isEmpty();
        }
    }

    private record Rule(String type, Pattern pattern) { }

    private static final List<Rule> RULES = List.of(
            new Rule("PRIVATE_KEY", Pattern.compile(
                    "-----BEGIN [A-Z ]*PRIVATE KEY-----[\\s\\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
            new Rule("AWS_ACCESS_KEY", Pattern.compile("\\bAKIA[0-9A-Z]{16}\\b")),
            new Rule("GITHUB_TOKEN", Pattern.compile("\\bgh[pousr]_[A-Za-z0-9]{36,}\\b")),
            new Rule("BITBUCKET_APP_PASSWORD", Pattern.compile("\\bATBB[A-Za-z0-9_\\-]{24,}\\b")),
            new Rule("JWT", Pattern.compile("\\beyJ[A-Za-z0-9_\\-]{10,}\\.[A-Za-z0-9_\\-]{10,}\\.[A-Za-z0-9_\\-]{10,}\\b")),
            new Rule("CONNECTION_STRING_PASSWORD", Pattern.compile(
                    "(?i)(?<=://[^\\s:/@]{1,64}:)[^\\s@/]{3,}(?=@)")),
            new Rule("GENERIC_SECRET", Pattern.compile(
                    "(?i)(?<=(password|passwd|secret|api[_-]?key|token)\\s{0,3}[:=]\\s{0,3}[\"']?)(?!\\[REDACTED)[^\\s\"'#]{6,}"))
    );

    public ScanResult scan(String text) {
        if (text == null || text.isEmpty()) {
            return new ScanResult(text == null ? "" : text, List.of());
        }
        String result = text;
        List<Finding> findings = new ArrayList<>();
        for (Rule rule : RULES) {
            Matcher m = rule.pattern().matcher(result);
            StringBuilder sb = new StringBuilder();
            boolean any = false;
            while (m.find()) {
                any = true;
                findings.add(new Finding(rule.type(), lineOf(result, m.start())));
                m.appendReplacement(sb, Matcher.quoteReplacement("[REDACTED:" + rule.type() + "]"));
            }
            if (any) {
                m.appendTail(sb);
                result = sb.toString();
            }
        }
        return new ScanResult(result, List.copyOf(findings));
    }

    /** Файлы, которые никогда не индексируются целиком. */
    public boolean isSecretFile(String path) {
        String p = path.toLowerCase();
        return p.endsWith(".env") || p.contains("/.env.") || p.startsWith(".env")
                || p.endsWith(".pem") || p.endsWith(".p12") || p.endsWith(".jks")
                || p.endsWith("id_rsa") || p.endsWith(".keystore");
    }

    private static int lineOf(String text, int offset) {
        int line = 1;
        for (int i = 0; i < offset && i < text.length(); i++) {
            if (text.charAt(i) == '\n') line++;
        }
        return line;
    }
}
