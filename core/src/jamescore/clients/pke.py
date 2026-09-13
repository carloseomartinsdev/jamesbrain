"""PKE HTTP client. Parallel to Tool Registry — PKE is not a Tool."""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import quote

import httpx

from jamescore.identity.principal import AuthenticatedPrincipal
from jamescore.settings import Settings

log = logging.getLogger("jamescore")


class PkeClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = settings.pke_api_url.rstrip("/")

    def _bearer(self, principal: AuthenticatedPrincipal) -> str:
        return f"Bearer {self._settings.pke_auth_prefix}{principal.sub}"

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/health", authenticated=False)

    def catalog(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/catalog", authenticated=False)

    def create_conversation(self, principal: AuthenticatedPrincipal, title: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if title:
            body["title"] = title
        return self._request("POST", "/api/v1/conversations", json=body, principal=principal)

    def list_messages(self, principal: AuthenticatedPrincipal, pke_conversation_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/v1/conversations/{quote(pke_conversation_id, safe='')}/messages",
            principal=principal,
        )

    def send_message(
        self,
        principal: AuthenticatedPrincipal,
        text: str,
        pke_conversation_id: str | None,
        client_request_id: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"text": text, "client_request_id": client_request_id}
        if pke_conversation_id:
            payload["conversation_id"] = pke_conversation_id
        return self._request("POST", "/api/v1/messages", json=payload, principal=principal)

    def answer_clarification(
        self,
        principal: AuthenticatedPrincipal,
        clarification_id: str,
        answer: dict[str, str],
        client_request_id: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"client_request_id": client_request_id}
        if answer.get("option_id"):
            payload["option_id"] = answer["option_id"]
        if answer.get("text"):
            payload["text"] = answer["text"]
        return self._request(
            "POST",
            f"/api/v1/clarifications/{quote(clarification_id, safe='')}/answer",
            json=payload,
            principal=principal,
        )

    def knowledge_graph(
        self,
        principal: AuthenticatedPrincipal,
        *,
        root_entity_id: str | None = None,
        depth: int = 2,
        current_only: bool = True,
        expand_entity_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {
            "depth": str(depth),
            "current_only": "true" if current_only else "false",
        }
        if root_entity_id:
            params["root_entity_id"] = root_entity_id
        if expand_entity_id:
            params["expand_entity_id"] = expand_entity_id
        return self._request("GET", "/api/v1/knowledge/graph", principal=principal, params=params)

    def knowledge_entity(
        self,
        principal: AuthenticatedPrincipal,
        entity_id: str,
        *,
        current_only: bool = True,
    ) -> dict[str, Any]:
        params = {"current_only": "true" if current_only else "false"}
        return self._request(
            "GET",
            f"/api/v1/knowledge/entities/{quote(entity_id, safe='')}",
            principal=principal,
            params=params,
        )

    def knowledge_search(
        self,
        principal: AuthenticatedPrincipal,
        q: str,
        *,
        type_key: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"q": q, "limit": str(limit)}
        if type_key:
            params["type"] = type_key
        return self._request("GET", "/api/v1/knowledge/search", principal=principal, params=params)

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        principal: AuthenticatedPrincipal | None = None,
        authenticated: bool = True,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        url = self._base + path
        headers = {"Accept": "application/json"}
        if authenticated:
            if principal is None:
                return {
                    "ok": False,
                    "http": 0,
                    "body": {
                        "error": {
                            "code": "PKE_UNAUTHENTICATED",
                            "message": "Não foi possível identificar você para esta conversa.",
                        }
                    },
                    "error_code": "PKE_UNAUTHENTICATED",
                }
            headers["Authorization"] = self._bearer(principal)
        timeout = httpx.Timeout(self._settings.pke_timeout_seconds, connect=5.0)
        error_code = None
        http_status = 0
        decoded: Any = {}
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.request(method, url, headers=headers, json=json, params=params)
            http_status = resp.status_code
            decoded = resp.json() if resp.content else {}
            err_obj = decoded.get("error") if isinstance(decoded, dict) else None
            err_code = err_obj.get("code") if isinstance(err_obj, dict) else None
            if http_status == 503:
                error_code = err_code or "PROVIDER_UNAVAILABLE"
            elif http_status >= 500:
                error_code = err_code or "PKE_ERROR"
            elif http_status == 401:
                error_code = "PKE_UNAUTHENTICATED"
            elif http_status == 404:
                error_code = err_code or "PKE_NOT_FOUND"
            elif http_status == 409:
                error_code = err_code or "PKE_CONFLICT"
            elif http_status == 422:
                error_code = err_code or "INVALID_PAYLOAD"
        except httpx.TimeoutException:
            error_code = "PKE_TIMEOUT"
        except httpx.HTTPError:
            error_code = "PKE_UNAVAILABLE"

        duration_ms = int((time.perf_counter() - started) * 1000)
        log.info(
            "james_pke op=%s %s user=%s http=%s duration_ms=%s error=%s",
            method,
            path,
            principal.sub if principal else "-",
            http_status,
            duration_ms,
            error_code or "ok",
        )
        ok = error_code is None and 200 <= http_status < 300
        return {"ok": ok, "http": http_status, "body": decoded, "error_code": error_code}
