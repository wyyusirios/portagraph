package ru.portagraph.agent;

/** Ошибка агентного ядра или LLM API. */
public class AgentException extends RuntimeException {
    public AgentException(String message) {
        super(message);
    }
}
