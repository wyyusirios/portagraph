package ru.portagraph.domain;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class AnalysisRunTest {

    @Test
    void followsAllowedLifecycle() {
        AnalysisRun run = new AnalysisRun(null, RunTrigger.MANUAL);
        run.moveTo(RunStatus.FETCHING);
        assertNotNull(run.getStartedAt());
        run.moveTo(RunStatus.INDEXING);
        run.moveTo(RunStatus.ANALYZING);
        run.moveTo(RunStatus.BUILDING_GRAPH);
        run.moveTo(RunStatus.COMPLETED);
        assertEquals(100, run.getProgress());
        assertFalse(run.isActive());
    }

    @Test
    void forbidsSkippingStages() {
        AnalysisRun run = new AnalysisRun(null, RunTrigger.WEBHOOK);
        assertThrows(IllegalStateException.class, () -> run.moveTo(RunStatus.COMPLETED));
    }

    @Test
    void failedRunCanBeRequeued() {
        AnalysisRun run = new AnalysisRun(null, RunTrigger.MANUAL);
        run.moveTo(RunStatus.FETCHING);
        run.fail("timeout");
        assertEquals("timeout", run.getErrorMessage());
        run.moveTo(RunStatus.QUEUED);
        assertTrue(run.isActive());
    }
}
