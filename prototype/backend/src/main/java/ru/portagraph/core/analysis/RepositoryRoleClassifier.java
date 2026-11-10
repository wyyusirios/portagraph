package ru.portagraph.core.analysis;

import java.util.Collection;
import java.util.Locale;

/**
 * Эвристическое определение роли репозитория по его файлам.
 * <p>
 * Пользователь не назначает роли вручную (требование паспорта). Эвристика даёт
 * первичную гипотезу и уверенность, которую затем уточняет агентное ядро по README и коду.
 */
public class RepositoryRoleClassifier {

    public enum Role { SERVICE, FRONTEND, LIBRARY, INFRASTRUCTURE, DOCUMENTATION, UNKNOWN }

    public record Classification(Role role, double confidence) { }

    public Classification classify(Collection<String> paths) {
        if (paths == null || paths.isEmpty()) {
            return new Classification(Role.UNKNOWN, 0.0);
        }
        int total = paths.size();
        int docs = 0, infra = 0;
        boolean dockerfile = false, entryPoint = false, webController = false;
        boolean frontendConfig = false, publishesArtifact = false;

        for (String raw : paths) {
            String p = raw.toLowerCase(Locale.ROOT);
            String name = p.substring(p.lastIndexOf('/') + 1);
            if (p.endsWith(".md") || p.endsWith(".adoc") || p.endsWith(".rst")) docs++;
            if (p.endsWith(".tf") || p.contains("helm/") || p.contains("k8s/") || p.contains("ansible/")) infra++;
            if (name.equals("dockerfile")) dockerfile = true;
            if (name.endsWith("application.java") || name.equals("main.go") || name.equals("main.py")
                    || name.equals("program.cs") || name.equals("app.py")) entryPoint = true;
            if (p.contains("controller") || p.contains("/routes/") || p.contains("/handlers/")
                    || name.equals("openapi.yaml") || name.equals("openapi.yml")) webController = true;
            if (name.startsWith("next.config") || name.startsWith("vite.config")
                    || name.equals("angular.json") || p.contains("/src/pages/") || p.contains("/app/page.")) {
                frontendConfig = true;
            }
            if (name.equals("setup.py") || name.equals("pyproject.toml") || p.contains("publishing")) {
                publishesArtifact = true;
            }
        }

        if ((double) docs / total > 0.7) return new Classification(Role.DOCUMENTATION, 0.8);
        if ((double) infra / total > 0.4) return new Classification(Role.INFRASTRUCTURE, 0.75);
        if (frontendConfig) return new Classification(Role.FRONTEND, 0.85);
        if (entryPoint && (webController || dockerfile)) return new Classification(Role.SERVICE, 0.9);
        if (entryPoint) return new Classification(Role.SERVICE, 0.6);
        if (publishesArtifact || !dockerfile) return new Classification(Role.LIBRARY, 0.5);
        return new Classification(Role.UNKNOWN, 0.2);
    }
}
