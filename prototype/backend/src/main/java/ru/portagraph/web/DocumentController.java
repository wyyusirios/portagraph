package ru.portagraph.web;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import ru.portagraph.service.DocumentationService;
import ru.portagraph.web.dto.Dto.DocumentView;
import ru.portagraph.web.dto.Dto.GenerateDocumentRequest;

import java.util.List;

@RestController
@RequestMapping("/api/projects/{projectId}/documents")
public class DocumentController {

    private final DocumentationService docs;

    public DocumentController(DocumentationService docs) {
        this.docs = docs;
    }

    @GetMapping
    public List<DocumentView> list(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId) {
        return docs.list(projectId, CurrentUser.id(jwt)).stream().map(DocumentView::of).toList();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public DocumentView generate(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId,
                                 @Valid @RequestBody GenerateDocumentRequest r) {
        return DocumentView.of(docs.generate(projectId, CurrentUser.id(jwt), r.type()));
    }

    @PostMapping("/{documentId}/approve")
    public DocumentView approve(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId,
                                @PathVariable Long documentId) {
        return DocumentView.of(docs.approve(projectId, CurrentUser.id(jwt), documentId));
    }
}
