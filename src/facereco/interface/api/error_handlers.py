"""Traduction des exceptions métier (Domain) en réponses HTTP (§12).

C'est la seule couche autorisée à connaître à la fois les exceptions du
Domain et le vocabulaire HTTP — le Domain lui-même ignore tout des codes 4xx.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from facereco.domain.exceptions import (
    AmbiguousFaceSelectionError,
    DomainError,
    EventNotFoundError,
    ImageQualityRejectedError,
    InvalidFaceIndexError,
    NoFaceDetectedError,
    SearchQuotaExceededError,
)

_STATUS_BY_EXCEPTION: list[tuple[type[DomainError], int]] = [
    (NoFaceDetectedError, status.HTTP_409_CONFLICT),
    (AmbiguousFaceSelectionError, status.HTTP_409_CONFLICT),
    (InvalidFaceIndexError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (ImageQualityRejectedError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (EventNotFoundError, status.HTTP_404_NOT_FOUND),
    (SearchQuotaExceededError, status.HTTP_429_TOO_MANY_REQUESTS),
]


def _make_handler(code: int) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def _handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    return _handler


def register_error_handlers(app: FastAPI) -> None:
    for exception_type, http_status in _STATUS_BY_EXCEPTION:
        app.add_exception_handler(exception_type, _make_handler(http_status))

    app.add_exception_handler(DomainError, _make_handler(status.HTTP_400_BAD_REQUEST))
