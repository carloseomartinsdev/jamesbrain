"""HTTP errors públicos. Sem stack trace."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from pke.product.api.v1.dtos import ApiErrorBody, ApiMessageStatus, ApiResponseType


class ApiHttpError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable


class ApiErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ApiResponseType = ApiResponseType.ERROR
    status: ApiMessageStatus = ApiMessageStatus.FAILED
    error: ApiErrorBody
