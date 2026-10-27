package ru.portagraph.web;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import ru.portagraph.domain.RunTrigger;
import ru.portagraph.repository.AnalysisRunRepository;
import ru.portagraph.service.AccessGuard;
import ru.portagraph.service.AnalysisPipeline;
import ru.portagraph.web.dto.Dto.RunView;

import java.util.List;

@RestController
@RequestMapping("/api/projects/{projectId}/analysis")
public class AnalysisController {

    private final AnalysisPipeline pipeline;
    private final AnalysisRunRepository runs;
    private final AccessGuard guard;

    public AnalysisController(AnalysisPipeline pipeline, AnalysisRunRepository runs, AccessGuard guard) {
        this.pipeline = pipeline;
        this.runs = runs;
        this.guard = guard;
    }

    /** Ручной перезапуск анализа. */
    @PostMapping
    @ResponseStatus(HttpStatus.ACCEPTED)
    public RunView start(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId) {
        guard.requireApprover(projectId, CurrentUser.id(jwt));
        return RunView.of(pipeline.enqueue(projectId, RunTrigger.MANUAL));
    }

    /** История и текущий прогресс (экран «Прогресс анализа» опрашивает этот метод). */
    @GetMapping
    public List<RunView> history(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId) {
        guard.requireMember(projectId, CurrentUser.id(jwt));
        return runs.findTop10ByProjectIdOrderByIdDesc(projectId).stream().map(RunView::of).toList();
    }
}
