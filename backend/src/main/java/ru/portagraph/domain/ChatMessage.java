package ru.portagraph.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/** Сообщение диалога. Ответ ассистента содержит ссылки на источники (citations). */
@Entity
@Table(name = "chat_messages")
@Getter
@Setter
@NoArgsConstructor
public class ChatMessage {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "session_id")
    private ChatSession session;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private MessageRole role;

    @Column(nullable = false, columnDefinition = "text")
    private String content;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt = Instant.now();

    @OneToMany(mappedBy = "message", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<Citation> citations = new ArrayList<>();

    public ChatMessage(ChatSession session, MessageRole role, String content) {
        this.session = session;
        this.role = role;
        this.content = content;
    }

    public void addCitation(SourceFile file, int startLine, int endLine, GraphNode node) {
        citations.add(new Citation(this, file, startLine, endLine, node));
    }
}
