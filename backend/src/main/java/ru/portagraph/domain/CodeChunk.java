package ru.portagraph.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.Array;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * Фрагмент файла с векторным представлением (embedding) для семантического поиска.
 * Вектор хранится в PostgreSQL в колонке типа {@code vector} расширения pgvector.
 */
@Entity
@Table(name = "code_chunks")
@Getter
@Setter
@NoArgsConstructor
public class CodeChunk {

    public static final int EMBEDDING_DIM = 1536;

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "source_file_id")
    private SourceFile sourceFile;

    @Column(name = "start_line", nullable = false)
    private int startLine;

    @Column(name = "end_line", nullable = false)
    private int endLine;

    /** Имя класса или функции, к которой относится фрагмент (если известно). */
    @Column(length = 300)
    private String symbol;

    @Column(nullable = false, columnDefinition = "text")
    private String content;

    @JdbcTypeCode(SqlTypes.VECTOR)
    @Array(length = EMBEDDING_DIM)
    @Column(columnDefinition = "vector(1536)")
    private float[] embedding;

    public CodeChunk(SourceFile sourceFile, int startLine, int endLine, String symbol, String content) {
        this.sourceFile = sourceFile;
        this.startLine = startLine;
        this.endLine = endLine;
        this.symbol = symbol;
        this.content = content;
    }
}
