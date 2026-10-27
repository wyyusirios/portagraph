package ru.portagraph.core.analysis;

import ru.portagraph.core.indexing.CodeChunker.SymbolSpan;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Резервный извлекатель символов (классы, интерфейсы, функции) для Java, Kotlin,
 * TypeScript/JavaScript и Python.
 * <p>
 * Основной разбор выполняет Tree-sitter в воркере анализа. Этот класс используется,
 * когда грамматики для языка нет: находит объявления и оценивает их границы по
 * балансу фигурных скобок (или по отступам для Python).
 */
public class SymbolExtractor {

    private static final Pattern BRACE_DECL = Pattern.compile(
            "^\\s*(?:export\\s+)?(?:public|private|protected|internal|abstract|final|static|data|sealed|default|\\s)*"
                    + "(class|interface|enum|record|object|function)\\s+([A-Za-z_$][\\w$]*)");
    private static final Pattern PY_DECL = Pattern.compile("^(\\s*)(class|def)\\s+([A-Za-z_]\\w*)");

    public List<SymbolSpan> extract(String language, String content) {
        String[] lines = content.split("\n", -1);
        return "python".equals(language) ? python(lines) : braces(lines);
    }

    private List<SymbolSpan> braces(String[] lines) {
        List<SymbolSpan> out = new ArrayList<>();
        for (int i = 0; i < lines.length; i++) {
            Matcher m = BRACE_DECL.matcher(lines[i]);
            if (!m.find()) continue;
            int depth = 0;
            boolean opened = false;
            int end = i;
            outer:
            for (int j = i; j < lines.length; j++) {
                for (char ch : stripStrings(lines[j]).toCharArray()) {
                    if (ch == '{') { depth++; opened = true; }
                    else if (ch == '}') {
                        depth--;
                        if (opened && depth == 0) { end = j; break outer; }
                    }
                }
                end = j;
                if (!opened && j > i + 3) { end = i; break; } // объявление без тела
            }
            out.add(new SymbolSpan(m.group(2), i + 1, end + 1));
        }
        return out;
    }

    private List<SymbolSpan> python(String[] lines) {
        List<SymbolSpan> out = new ArrayList<>();
        for (int i = 0; i < lines.length; i++) {
            Matcher m = PY_DECL.matcher(lines[i]);
            if (!m.find()) continue;
            int indent = m.group(1).length();
            int end = i;
            for (int j = i + 1; j < lines.length; j++) {
                String l = lines[j];
                if (l.isBlank()) continue;
                int ind = l.length() - l.stripLeading().length();
                if (ind <= indent) break;
                end = j;
            }
            out.add(new SymbolSpan(m.group(3), i + 1, end + 1));
        }
        return out;
    }

    private static String stripStrings(String line) {
        return line.replaceAll("\"(\\\\.|[^\"\\\\])*\"", "\"\"").replaceAll("//.*$", "");
    }
}
