package ru.portagraph.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import ru.portagraph.agent.AgentException;
import ru.portagraph.service.NotFoundException;
import ru.portagraph.web.dto.Dto.ErrorView;

import java.util.NoSuchElementException;

/** Единый формат ошибок API. */
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler({NotFoundException.class, NoSuchElementException.class})
    ResponseEntity<ErrorView> notFound(RuntimeException e) {
        return of(HttpStatus.NOT_FOUND, e.getMessage());
    }

    @ExceptionHandler(AccessDeniedException.class)
    ResponseEntity<ErrorView> forbidden(AccessDeniedException e) {
        return of(HttpStatus.FORBIDDEN, e.getMessage());
    }

    @ExceptionHandler({BadCredentialsException.class, SecurityException.class})
    ResponseEntity<ErrorView> unauthorized(RuntimeException e) {
        return of(HttpStatus.UNAUTHORIZED, e.getMessage());
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ErrorView> badRequest(IllegalArgumentException e) {
        return of(HttpStatus.BAD_REQUEST, e.getMessage());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ErrorView> invalid(MethodArgumentNotValidException e) {
        String msg = e.getBindingResult().getFieldErrors().stream()
                .map(f -> f.getField() + ": " + f.getDefaultMessage()).findFirst().orElse("Некорректный запрос");
        return of(HttpStatus.BAD_REQUEST, msg);
    }

    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<ErrorView> conflict(IllegalStateException e) {
        return of(HttpStatus.CONFLICT, e.getMessage());
    }

    @ExceptionHandler(AgentException.class)
    ResponseEntity<ErrorView> agent(AgentException e) {
        return of(HttpStatus.BAD_GATEWAY, "AI-сервис временно недоступен: " + e.getMessage());
    }

    private static ResponseEntity<ErrorView> of(HttpStatus s, String msg) {
        return ResponseEntity.status(s).body(new ErrorView(s.value(), s.getReasonPhrase(), msg));
    }
}
