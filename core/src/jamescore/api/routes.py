from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from jamescore import __version__
from jamescore.application.envelopes import ClarificationRequest, ConversationCreateRequest, TurnRequest
from jamescore.application.orchestrator import Orchestrator
from jamescore.identity.assertion import IdentityError, parse_bearer, verify_assertion
from jamescore.identity.principal import AuthenticatedPrincipal

router = APIRouter()


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def require_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedPrincipal:
    settings: Settings = request.app.state.settings
    token = parse_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail={"code": "IDENTITY_MISSING", "message": "Identity assertion required."})
    try:
        return verify_assertion(settings, token)
    except IdentityError as exc:
        status = 401
        raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message}) from exc


@router.get("/v1/health")
def health(orch: Orchestrator = Depends(get_orchestrator)) -> dict:
    body = orch.health()
    body["version"] = __version__
    return body


@router.get("/v1/catalog")
def catalog(orch: Orchestrator = Depends(get_orchestrator)):
    result = orch.catalog()
    if not result.get("ok"):
        err = result.get("error") if isinstance(result.get("error"), dict) else {}
        raise HTTPException(
            status_code=503,
            detail={
                "code": err.get("code") or "PKE_UNAVAILABLE",
                "message": err.get("message") or "Catálogo do PKE indisponível.",
            },
        )
    return result["catalog"]


@router.post("/v1/conversations")
def create_conversation(
    payload: ConversationCreateRequest,
    principal: AuthenticatedPrincipal = Depends(require_principal),
    orch: Orchestrator = Depends(get_orchestrator),
) -> dict:
    return orch.create_conversation(principal, payload.title)


@router.get("/v1/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: str,
    principal: AuthenticatedPrincipal = Depends(require_principal),
    orch: Orchestrator = Depends(get_orchestrator),
) -> dict:
    result = orch.list_messages(principal, conversation_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return {"messages": result["messages"]}


@router.post("/v1/turns")
def turns(
    payload: TurnRequest,
    principal: AuthenticatedPrincipal = Depends(require_principal),
    orch: Orchestrator = Depends(get_orchestrator),
) -> JSONResponse:
    text = (payload.text or "").strip()
    if text == "":
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_PAYLOAD", "message": "Escreva uma mensagem."}},
        )
    james_id = payload.james_conversation_id or payload.conversation_id
    env = orch.handle_turn(principal, text, james_id, trace=payload.trace)
    return _envelope_response(env)


@router.post("/v1/clarifications/{clarification_id}/answer")
def answer_clarification(
    clarification_id: str,
    payload: ClarificationRequest,
    principal: AuthenticatedPrincipal = Depends(require_principal),
    orch: Orchestrator = Depends(get_orchestrator),
) -> JSONResponse:
    text = (payload.text or "").strip()
    option_id = (payload.option_id or "").strip()
    if text == "" and option_id == "":
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_PAYLOAD", "message": "Informe uma opção ou um texto."}},
        )
    cid = payload.clarification_id or clarification_id
    env = orch.answer_clarification(principal, cid, text, option_id, trace=payload.trace)
    return _envelope_response(env)


def _envelope_response(env) -> JSONResponse:
    body = env.model_dump()
    if env.outcome == "technical_error":
        return JSONResponse(status_code=503, content=body)
    return JSONResponse(status_code=200, content=body)
