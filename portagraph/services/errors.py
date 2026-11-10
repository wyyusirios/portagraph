"""Ошибки бизнес-логики. Веб-слой превращает их в HTTP-ответы с понятным текстом."""


class AppError(Exception):
    status = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BadRequest(AppError):
    status = 400


class Unauthorized(AppError):
    status = 401


class Forbidden(AppError):
    status = 403


class NotFound(AppError):
    status = 404


class Conflict(AppError):
    status = 409
