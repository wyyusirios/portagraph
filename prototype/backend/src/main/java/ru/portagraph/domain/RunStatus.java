package ru.portagraph.domain;

/** Этап задачи анализа (см. диаграмму состояний). */
public enum RunStatus {
    QUEUED, FETCHING, INDEXING, ANALYZING, BUILDING_GRAPH, COMPLETED, FAILED, CANCELLED
}
