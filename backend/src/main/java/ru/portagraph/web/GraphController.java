package ru.portagraph.web;

import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import ru.portagraph.service.GraphService;
import ru.portagraph.web.dto.Dto.GraphView;
import ru.portagraph.web.dto.Dto.VerifyNodeRequest;

@RestController
@RequestMapping("/api/projects/{projectId}/graph")
public class GraphController {

    private final GraphService graphs;

    public GraphController(GraphService graphs) {
        this.graphs = graphs;
    }

    /** Режим визуализации: {@code overview} — карта системы, {@code detailed} — граф зависимостей кода. */
    @GetMapping
    public GraphView graph(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId,
                           @RequestParam(defaultValue = "overview") String mode) {
        Long uid = CurrentUser.id(jwt);
        return GraphView.of("detailed".equalsIgnoreCase(mode)
                ? graphs.detailed(projectId, uid)
                : graphs.overview(projectId, uid));
    }

    @PostMapping("/nodes/{nodeId}/verify")
    public void verify(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId, @PathVariable Long nodeId,
                       @Valid @RequestBody VerifyNodeRequest r) {
        graphs.verifyNode(projectId, CurrentUser.id(jwt), nodeId, r.correctedDescription());
    }
}
