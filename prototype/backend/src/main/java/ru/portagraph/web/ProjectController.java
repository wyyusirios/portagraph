package ru.portagraph.web;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import ru.portagraph.service.ProjectService;
import ru.portagraph.web.dto.Dto.AddMemberRequest;
import ru.portagraph.web.dto.Dto.CreateProjectRequest;
import ru.portagraph.web.dto.Dto.ProjectView;

import java.util.List;

@RestController
@RequestMapping("/api/projects")
public class ProjectController {

    private final ProjectService projects;

    public ProjectController(ProjectService projects) {
        this.projects = projects;
    }

    @GetMapping
    public List<ProjectView> list(@AuthenticationPrincipal Jwt jwt) {
        return projects.listForUser(CurrentUser.id(jwt)).stream().map(ProjectView::of).toList();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ProjectView create(@AuthenticationPrincipal Jwt jwt, @Valid @RequestBody CreateProjectRequest r) {
        return ProjectView.of(projects.create(CurrentUser.id(jwt), r.name(), r.description()));
    }

    @GetMapping("/{projectId}")
    public ProjectView get(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId) {
        return ProjectView.of(projects.get(projectId, CurrentUser.id(jwt)));
    }

    @PostMapping("/{projectId}/members")
    @ResponseStatus(HttpStatus.CREATED)
    public void addMember(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId,
                          @Valid @RequestBody AddMemberRequest r) {
        projects.addMember(projectId, CurrentUser.id(jwt), r.email(), r.role());
    }

    @DeleteMapping("/{projectId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void archive(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId) {
        projects.archive(projectId, CurrentUser.id(jwt));
    }
}
