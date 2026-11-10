package ru.portagraph.core.indexing;

import java.util.ArrayList;
import java.util.List;

/**
 * Нарезка файла на фрагменты (чанки) для RAG-индекса.
 * <p>
 * Если парсер (Tree-sitter) нашёл границы символов — классов и функций, — фрагменты
 * режутся по ним. Иначе используется окно фиксированного размера с перекрытием,
 * чтобы контекст на стыке не терялся. Номера строк сохраняются для ссылок на исходник.
 */
public class CodeChunker {

    /** Границы символа, найденные парсером (строки с 1, включительно). */
    public record SymbolSpan(String name, int startLine, int endLine) { }

    /** Фрагмент кода с привязкой к строкам файла. */
    public record Chunk(int startLine, int endLine, String symbol, String content) { }

    private final int windowLines;
    private final int overlapLines;

    public CodeChunker(int windowLines, int overlapLines) {
        if (windowLines < 5) throw new IllegalArgumentException("Окно должно быть не меньше 5 строк");
        if (overlapLines < 0 || overlapLines >= windowLines) {
            throw new IllegalArgumentException("Перекрытие должно быть в диапазоне [0, окно)");
        }
        this.windowLines = windowLines;
        this.overlapLines = overlapLines;
    }

    public List<Chunk> chunk(String content, List<SymbolSpan> symbols) {
        String[] lines = content.split("\n", -1);
        List<Chunk> result = new ArrayList<>();
        if (symbols != null && !symbols.isEmpty()) {
            for (SymbolSpan s : symbols) {
                int from = Math.max(1, s.startLine());
                int to = Math.min(lines.length, s.endLine());
                if (from > to) continue;
                // большие символы режем окнами, сохраняя имя символа
                result.addAll(window(lines, from, to, s.name()));
            }
            return result;
        }
        return window(lines, 1, lines.length, null);
    }

    private List<Chunk> window(String[] lines, int from, int to, String symbol) {
        List<Chunk> out = new ArrayList<>();
        int start = from;
        while (start <= to) {
            int end = Math.min(to, start + windowLines - 1);
            out.add(new Chunk(start, end, symbol, join(lines, start, end)));
            if (end == to) break;
            start = end - overlapLines + 1;
        }
        return out;
    }

    private static String join(String[] lines, int from, int to) {
        StringBuilder sb = new StringBuilder();
        for (int i = from; i <= to; i++) {
            sb.append(lines[i - 1]);
            if (i < to) sb.append('\n');
        }
        return sb.toString();
    }
}
