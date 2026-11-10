package ru.portagraph.web;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import ru.portagraph.service.ImpactAnalysisService;
import ru.portagraph.web.dto.Dto.ImpactRequest;
import ru.portagraph.web.dto.Dto.ImpactView;

import java.util.List;

@RestController
@RequestMapping("/api/projects/{projectId}/impact")
public class ImpactController {

    private final ImpactAnalysisService impact;

    public ImpactController(ImpactAnalysisService impact) {
        this.impact = impact;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ImpactView analyze(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId,
                              @Valid @RequestBody ImpactRequest r) {
        return ImpactView.of(impact.analyze(projectId, CurrentUser.id(jwt), r.changeDescription(),
                r.nodeIds(), r.depth()));
    }

    @GetMapping
    public List<ImpactView> history(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId) {
        return impact.history(projectId, CurrentUser.id(jwt)).stream().map(ImpactView::of).toList();
    }
}
