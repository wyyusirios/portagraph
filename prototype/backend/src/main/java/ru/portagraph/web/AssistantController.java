package ru.portagraph.web;

import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import ru.portagraph.service.QuestionAnsweringService;
import ru.portagraph.web.dto.Dto.AnswerView;
import ru.portagraph.web.dto.Dto.AskRequest;

@RestController
@RequestMapping("/api/projects/{projectId}/assistant")
public class AssistantController {

    private final QuestionAnsweringService qa;

    public AssistantController(QuestionAnsweringService qa) {
        this.qa = qa;
    }

    @PostMapping("/ask")
    public AnswerView ask(@AuthenticationPrincipal Jwt jwt, @PathVariable Long projectId,
                          @Valid @RequestBody AskRequest r) {
        return AnswerView.of(qa.ask(projectId, CurrentUser.id(jwt), r.sessionId(), r.question()));
    }
}
