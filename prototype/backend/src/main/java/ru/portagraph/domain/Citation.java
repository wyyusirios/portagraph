package ru.portagraph.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/** Ссылка ответа ассистента на конкретные строки исходного файла и узел графа. */
@Entity
@Table(name = "citations")
@Getter
@Setter
@NoArgsConstructor
public class Citation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "message_id")
    private ChatMessage message;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "source_file_id")
    private SourceFile sourceFile;

    @Column(name = "start_line", nullable = false)
    private int startLine;

    @Column(name = "end_line", nullable = false)
    private int endLine;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "node_id")
    private GraphNode node;

    public Citation(ChatMessage message, SourceFile sourceFile, int startLine, int endLine, GraphNode node) {
        this.message = message;
        this.sourceFile = sourceFile;
        this.startLine = startLine;
        this.endLine = endLine;
        this.node = node;
    }
}
