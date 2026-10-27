package ru.portagraph.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.portagraph.agent.AgentRuntime;
import ru.portagraph.agent.AgentRuntime.ContextSnippet;
import ru.portagraph.agent.AgentRuntime.GroundedAnswer;
import ru.portagraph.agent.EmbeddingClient;
import ru.portagraph.domain.*;
import ru.portagraph.repository.ChatSessionRepository;
import ru.portagraph.repository.CodeChunkRepository;
import ru.portagraph.repository.ProjectRepository;
import ru.portagraph.repository.UserRepository;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * AI-поиск и ответы на вопросы по проекту с привязкой к исходному коду (UC-09).
 * RAG: вопрос → embedding → ближайшие фрагменты (pgvector) → агент → ответ со ссылками.
 */
@Service
public class QuestionAnsweringService {

    static final int TOP_K = 12;
    /** Ниже этого порога ответ помечается как недостаточно обоснованный. */
    static final double MIN_CONFIDENCE = 0.4;

    private final EmbeddingClient embeddings;
    private final CodeChunkRepository chunks;
    private final AgentRuntime agent;
    private final ChatSessionRepository sessions;
    private final ProjectRepository projects;
    private final UserRepository users;
    private final AccessGuard guard;

    public QuestionAnsweringService(EmbeddingClient embeddings, CodeChunkRepository chunks, AgentRuntime agent,
                                    ChatSessionRepository sessions, ProjectRepository projects,
                                    UserRepository users, AccessGuard guard) {
        this.embeddings = embeddings;
        this.chunks = chunks;
        this.agent = agent;
        this.sessions = sessions;
        this.projects = projects;
        this.users = users;
        this.guard = guard;
    }

    @Transactional
    public ChatMessage ask(Long projectId, Long userId, Long sessionId, String question) {
        guard.requireMember(projectId, userId);
        if (question == null || question.isBlank()) {
            throw new IllegalArgumentException("Вопрос не может быть пустым");
        }
        ChatSession session = sessionId == null
                ? sessions.save(new ChatSession(projects.getReferenceById(projectId),
                        users.getReferenceById(userId), shorten(question)))
                : sessions.findById(sessionId)
                        .filter(s -> s.getProject().getId().equals(projectId) && s.getUser().getId().equals(userId))
                        .orElseThrow(() -> new NotFoundException("Диалог не найден"));
        session.addMessage(MessageRole.USER, question.strip());

        String vector = EmbeddingClient.toPgVector(embeddings.embed(question));
        List<CodeChunk> found = chunks.findNearest(projectId, vector, TOP_K);
        if (found.isEmpty()) {
            return session.addMessage(MessageRole.ASSISTANT,
                    "В проиндексированных материалах проекта нет данных для ответа на этот вопрос.");
        }
        List<ContextSnippet> snippets = found.stream().map(c -> new ContextSnippet(c.getId(),
                c.getSourceFile().getPath(), c.getStartLine(), c.getEndLine(), c.getContent())).toList();
        GroundedAnswer answer = agent.answer(question, snippets);

        String text = answer.confidence() < MIN_CONFIDENCE
                ? answer.text() + "\n\n⚠ Ответ основан на неполных данных — проверьте указанные источники."
                : answer.text();
        ChatMessage reply = session.addMessage(MessageRole.ASSISTANT, text);

        Map<Long, CodeChunk> byId = found.stream().collect(Collectors.toMap(CodeChunk::getId, Function.identity()));
        for (Long id : answer.usedChunkIds()) {
            CodeChunk c = byId.get(id);
            if (c != null) { // ссылки только на реально переданные агенту фрагменты
                reply.addCitation(c.getSourceFile(), c.getStartLine(), c.getEndLine(), null);
            }
        }
        return reply;
    }

    private static String shorten(String q) {
        String s = q.strip().replaceAll("\\s+", " ");
        return s.length() <= 80 ? s : s.substring(0, 77) + "...";
    }
}
