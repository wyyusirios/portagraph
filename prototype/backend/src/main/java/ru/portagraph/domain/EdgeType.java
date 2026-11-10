package ru.portagraph.domain;

/** Тип связи между узлами графа. */
public enum EdgeType {
    CONTAINS, DEPENDS_ON, IMPORTS, CALLS_HTTP, PUBLISHES, CONSUMES, READS_WRITES, IMPLEMENTS
}
