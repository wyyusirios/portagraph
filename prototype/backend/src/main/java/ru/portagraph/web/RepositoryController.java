package ru.portagraph.web;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import ru.portagraph.service.RepositoryConnectionService;
import ru.portagraph.service.RepositoryConnectionService.ConnectResult;
import ru.portagraph.web.dto.Dto.ConnectRepositoriesRequest;
import ru.portagraph.web.dto.Dto.RepositoryView;

import java.util.List;

@RestController
@RequestMapping("/api/projects/{projectId}/repositories")
public class RepositoryController {

    private final RepositoryConnectionService service;

    public RepositoryController(RepositoryConnectionService service) {
        this.service = service;
    }

    @GetMapping
    public List<RepositoryView> list(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId) {
        return service.list(projectId, CurrentUser.id(jwt)).stream().map(RepositoryView::of).toList();
    }

    /** Подключение набора репозиториев одним запросом; результат — по каждому адресу. */
    @PostMapping
    public List<ConnectResult> connect(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId,
                                       @Valid @RequestBody ConnectRepositoriesRequest r) {
        return service.connect(projectId, CurrentUser.id(jwt), r.urls(), r.accessToken());
    }

    @DeleteMapping("/{repositoryId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void disconnect(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId,
                           @PathVariable Long repositoryId) {
        service.disconnect(projectId, CurrentUser.id(jwt), repositoryId);
    }
}
