package ru.portagraph.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import ru.portagraph.service.WebhookService;
import ru.portagraph.service.WebhookService.Outcome;
import ru.portagraph.service.WebhookService.PushEvent;

import java.io.IOException;

/** Приём push-событий. Тело читается «как есть» — подпись считается по сырым байтам. */
@RestController
@RequestMapping("/api/webhooks")
public class WebhookController {

    private final WebhookService webhooks;
    private final ObjectMapper json;

    public WebhookController(WebhookService webhooks, ObjectMapper json) {
        this.webhooks = webhooks;
        this.json = json;
    }

    @PostMapping("/github/{repositoryId}")
    public ResponseEntity<String> github(@PathVariable Long repositoryId, @RequestBody byte[] body,
                                         @RequestHeader("X-GitHub-Event") String event,
                                         @RequestHeader("X-GitHub-Delivery") String delivery,
                                         @RequestHeader("X-Hub-Signature-256") String signature) throws IOException {
        if (!"push".equals(event)) {
            return ResponseEntity.accepted().body("ignored");
        }
        JsonNode p = json.readTree(body);
        String branch = p.path("ref").asText().replaceFirst("^refs/heads/", "");
        Outcome o = webhooks.handlePush(repositoryId, body, signature,
                new PushEvent(delivery, branch, p.path("after").asText()));
        return ResponseEntity.accepted().body(o.name());
    }

    @PostMapping("/bitbucket/{repositoryId}")
    public ResponseEntity<String> bitbucket(@PathVariable Long repositoryId, @RequestBody byte[] body,
                                            @RequestHeader("X-Request-UUID") String delivery,
                                            @RequestHeader("X-Hub-Signature") String signature) throws IOException {
        JsonNode change = json.readTree(body).path("push").path("changes").path(0).path("new");
        Outcome o = webhooks.handlePush(repositoryId, body, signature,
                new PushEvent(delivery, change.path("name").asText(), change.path("target").path("hash").asText()));
        return ResponseEntity.accepted().body(o.name());
    }
}
