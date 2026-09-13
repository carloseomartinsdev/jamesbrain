"""Rotas públicas PKE API v1."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import JSONResponse

from pke import __version__ as PKE_VERSION
from pke.product.api.v1.dtos import (
    ApiAuthLoginRequest,
    ApiAuthRegisterRequest,
    ApiAuthSessionResponse,
    ApiCatalog,
    ApiClarificationAnswerRequest,
    ApiConversation,
    ApiConversationSummary,
    ApiCreateConversationRequest,
    ApiCurrentUser,
    ApiHealth,
    ApiMessage,
    ApiMessageRequest,
    ApiMessageResponse,
)
from pke.product.api.v1.errors import ApiHttpError
from pke.ontology.registry import OntologyRegistry
from pke.product.auth import AuthError, AuthUser, ProductAuthResolver
from pke.product.knowledge.dtos import (
    KnowledgeEntityResponse,
    KnowledgeGraphResponse,
    KnowledgeSearchResponse,
)
from pke.product.knowledge.inspector import (
    KnowledgeInspector,
    KnowledgeInvalidId,
    KnowledgeNotFound,
)
from pke.product.conversation.orchestrator import (
    ClarificationConflict,
    ClarificationNotFound,
    ConversationNotFound,
    ConversationOrchestrator,
    IdempotencyConflict,
    IdempotencyInProgress,
    ProductStoreUnavailable,
)
from pke.product.conversation.recovery import OperationRequiresReconciliation

router = APIRouter(prefix="/api/v1")


def get_auth_resolver() -> ProductAuthResolver:
    raise RuntimeError("auth resolver não configurado")


def get_auth_service():
    raise RuntimeError("auth service não configurado")


def get_orchestrator() -> ConversationOrchestrator:
    raise RuntimeError("orchestrator não configurado")


def get_ontology() -> OntologyRegistry:
    raise RuntimeError("ontology não configurada")


def get_knowledge_inspector() -> KnowledgeInspector:
    raise RuntimeError("knowledge inspector não configurado")


def get_auth(
    authorization: Annotated[str | None, Header()] = None,
    resolver: Annotated[ProductAuthResolver, Depends(get_auth_resolver)] = None,  # type: ignore[assignment]
) -> AuthUser:
    assert resolver is not None
    try:
        return resolver.resolve(authorization)
    except AuthError as exc:
        raise ApiHttpError(exc.status_code, exc.code, exc.message) from exc


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, rest = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return rest.strip() or None


def _user_dto(user: AuthUser) -> ApiCurrentUser:
    return ApiCurrentUser(
        id=user.id,
        display_name=user.display_name,
        auth_mode=user.auth_mode,
        username=user.username,
    )


@router.get("/health", response_model=ApiHealth)
def health() -> ApiHealth:
    return ApiHealth(status="ok", version=PKE_VERSION)


@router.get("/catalog", response_model=ApiCatalog)
def catalog(ontology: Annotated[OntologyRegistry, Depends(get_ontology)]) -> ApiCatalog:
    from pke.ontology.inspect import inspect_catalog

    return ApiCatalog.model_validate(inspect_catalog(ontology))


@router.post("/auth/register", response_model=ApiAuthSessionResponse, status_code=status.HTTP_201_CREATED)
def register(
    body: ApiAuthRegisterRequest,
    auth_service=Depends(get_auth_service),
) -> ApiAuthSessionResponse:
    if auth_service is None:
        raise ApiHttpError(503, "AUTH_MISCONFIGURED", "Registro indisponível neste modo.")
    try:
        user = auth_service.register(body.username, body.password, body.display_name)
        session = auth_service.login(body.username, body.password)
    except AuthError as exc:
        raise ApiHttpError(exc.status_code, exc.code, exc.message) from exc
    return ApiAuthSessionResponse(
        access_token=session.token,
        expires_at=session.expires_at,
        user=ApiCurrentUser(
            id=user.id,
            display_name=user.display_name,
            auth_mode="session",
            username=user.username,
        ),
    )


@router.post("/auth/login", response_model=ApiAuthSessionResponse)
def login(
    body: ApiAuthLoginRequest,
    auth_service=Depends(get_auth_service),
) -> ApiAuthSessionResponse:
    if auth_service is None:
        raise ApiHttpError(503, "AUTH_MISCONFIGURED", "Login indisponível neste modo.")
    try:
        session = auth_service.login(body.username, body.password)
        user = auth_service.user_public(session.user_id)
    except AuthError as exc:
        raise ApiHttpError(exc.status_code, exc.code, exc.message) from exc
    if user is None:
        raise ApiHttpError(401, "UNAUTHENTICATED", "Usuário ou senha inválidos.")
    return ApiAuthSessionResponse(
        access_token=session.token,
        expires_at=session.expires_at,
        user=ApiCurrentUser(
            id=user.id,
            display_name=user.display_name,
            auth_mode="session",
            username=user.username,
        ),
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    authorization: Annotated[str | None, Header()] = None,
    auth_service=Depends(get_auth_service),
) -> None:
    if auth_service is None:
        return None
    auth_service.logout(_extract_bearer(authorization))
    return None


@router.get("/me", response_model=ApiCurrentUser)
def me(user: Annotated[AuthUser, Depends(get_auth)]) -> ApiCurrentUser:
    return _user_dto(user)


@router.get("/conversations", response_model=list[ApiConversationSummary])
def list_conversations(
    user: Annotated[AuthUser, Depends(get_auth)],
    orchestrator: Annotated[ConversationOrchestrator, Depends(get_orchestrator)],
) -> list[ApiConversationSummary]:
    return orchestrator.list_conversations(user)


@router.post(
    "/conversations",
    response_model=ApiConversation,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    user: Annotated[AuthUser, Depends(get_auth)],
    orchestrator: Annotated[ConversationOrchestrator, Depends(get_orchestrator)],
    body: ApiCreateConversationRequest | None = None,
) -> ApiConversation:
    title = body.title if body is not None else None
    return orchestrator.create_conversation(user, title)


@router.get("/conversations/{conversation_id}", response_model=ApiConversation)
def get_conversation(
    conversation_id: str,
    user: Annotated[AuthUser, Depends(get_auth)],
    orchestrator: Annotated[ConversationOrchestrator, Depends(get_orchestrator)],
) -> ApiConversation:
    try:
        return orchestrator.get_conversation(user, conversation_id)
    except ConversationNotFound as exc:
        raise ApiHttpError(404, "CONVERSATION_NOT_FOUND", "Conversa não encontrada.") from exc


@router.get("/conversations/{conversation_id}/messages", response_model=list[ApiMessage])
def list_messages(
    conversation_id: str,
    user: Annotated[AuthUser, Depends(get_auth)],
    orchestrator: Annotated[ConversationOrchestrator, Depends(get_orchestrator)],
) -> list[ApiMessage]:
    try:
        return orchestrator.list_messages(user, conversation_id)
    except ConversationNotFound as exc:
        raise ApiHttpError(404, "CONVERSATION_NOT_FOUND", "Conversa não encontrada.") from exc


@router.post("/messages", response_model=ApiMessageResponse)
def post_message(
    body: ApiMessageRequest,
    user: Annotated[AuthUser, Depends(get_auth)],
    orchestrator: Annotated[ConversationOrchestrator, Depends(get_orchestrator)],
) -> ApiMessageResponse | JSONResponse:
    text = body.text.strip()
    if not text:
        raise ApiHttpError(422, "INVALID_PAYLOAD", "O texto da mensagem é obrigatório.")
    try:
        response = orchestrator.send_message(user, body.model_copy(update={"text": text}))
    except ConversationNotFound as exc:
        raise ApiHttpError(404, "CONVERSATION_NOT_FOUND", "Conversa não encontrada.") from exc
    except IdempotencyConflict as exc:
        raise ApiHttpError(
            409,
            "IDEMPOTENCY_KEY_CONFLICT",
            "Este pedido já foi usado com outro conteúdo.",
            retryable=False,
        ) from exc
    except IdempotencyInProgress as exc:
        raise ApiHttpError(
            409,
            "IDEMPOTENCY_IN_PROGRESS",
            "Seu pedido ainda está sendo processado. Tente de novo em instantes.",
            retryable=True,
        ) from exc
    except OperationRequiresReconciliation as exc:
        raise ApiHttpError(
            409,
            "OPERATION_RECOVERY_REQUIRED",
            "Não foi possível confirmar o resultado deste pedido. Não tente reenviar o mesmo conteúdo; verifique o histórico da conversa.",
            retryable=False,
        ) from exc
    except ProductStoreUnavailable as exc:
        raise ApiHttpError(
            503,
            "PRODUCT_UNAVAILABLE",
            "Serviço temporariamente indisponível. Tente mais tarde.",
            retryable=True,
        ) from exc
    return _with_http_status(response)


@router.post("/clarifications/{clarification_id}/answer", response_model=ApiMessageResponse)
def answer_clarification(
    clarification_id: str,
    body: ApiClarificationAnswerRequest,
    user: Annotated[AuthUser, Depends(get_auth)],
    orchestrator: Annotated[ConversationOrchestrator, Depends(get_orchestrator)],
) -> ApiMessageResponse:
    try:
        response = orchestrator.answer_clarification(user, clarification_id, body)
    except ClarificationNotFound as exc:
        raise ApiHttpError(404, "CLARIFICATION_NOT_FOUND", "Clarificação não encontrada.") from exc
    except ClarificationConflict as exc:
        raise ApiHttpError(
            409,
            "CLARIFICATION_ANSWERED",
            "Essa clarificação já foi respondida.",
            retryable=False,
        ) from exc
    except IdempotencyConflict as exc:
        raise ApiHttpError(
            409,
            "IDEMPOTENCY_KEY_CONFLICT",
            "Este pedido já foi usado com outro conteúdo.",
            retryable=False,
        ) from exc
    except IdempotencyInProgress as exc:
        raise ApiHttpError(
            409,
            "IDEMPOTENCY_IN_PROGRESS",
            "Seu pedido ainda está sendo processado. Tente de novo em instantes.",
            retryable=True,
        ) from exc
    except OperationRequiresReconciliation as exc:
        raise ApiHttpError(
            409,
            "OPERATION_RECOVERY_REQUIRED",
            "Não foi possível confirmar o resultado deste pedido. Não tente reenviar o mesmo conteúdo; verifique o histórico da conversa.",
            retryable=False,
        ) from exc
    except ProductStoreUnavailable as exc:
        raise ApiHttpError(
            503,
            "PRODUCT_UNAVAILABLE",
            "Serviço temporariamente indisponível. Tente mais tarde.",
            retryable=True,
        ) from exc
    except ValueError as exc:
        raise ApiHttpError(422, "INVALID_PAYLOAD", "Informe uma opção ou um texto.") from exc
    return _with_http_status(response)


@router.get("/knowledge/graph", response_model=KnowledgeGraphResponse)
def knowledge_graph(
    user: Annotated[AuthUser, Depends(get_auth)],
    inspector: Annotated[KnowledgeInspector, Depends(get_knowledge_inspector)],
    root_entity_id: Annotated[str | None, Query(max_length=128)] = None,
    depth: Annotated[int, Query(ge=1, le=3)] = 2,
    current_only: bool = True,
    expand_entity_id: Annotated[str | None, Query(max_length=128)] = None,
) -> KnowledgeGraphResponse:
    try:
        return inspector.graph(
            user.id,
            root_entity_id=root_entity_id,
            depth=depth,
            current_only=current_only,
            expand_entity_id=expand_entity_id,
        )
    except KnowledgeInvalidId as exc:
        raise ApiHttpError(422, "INVALID_PAYLOAD", "Identificador inválido.") from exc
    except KnowledgeNotFound as exc:
        raise ApiHttpError(404, "ENTITY_NOT_FOUND", "Entidade não encontrada.") from exc


@router.get("/knowledge/entities/{entity_id}", response_model=KnowledgeEntityResponse)
def knowledge_entity(
    entity_id: str,
    user: Annotated[AuthUser, Depends(get_auth)],
    inspector: Annotated[KnowledgeInspector, Depends(get_knowledge_inspector)],
    current_only: bool = True,
) -> KnowledgeEntityResponse:
    try:
        return inspector.entity(user.id, entity_id, current_only=current_only)
    except KnowledgeInvalidId as exc:
        raise ApiHttpError(422, "INVALID_PAYLOAD", "Identificador inválido.") from exc
    except KnowledgeNotFound as exc:
        raise ApiHttpError(404, "ENTITY_NOT_FOUND", "Entidade não encontrada.") from exc


@router.get("/knowledge/search", response_model=KnowledgeSearchResponse)
def knowledge_search(
    user: Annotated[AuthUser, Depends(get_auth)],
    inspector: Annotated[KnowledgeInspector, Depends(get_knowledge_inspector)],
    q: Annotated[str, Query(max_length=200)] = "",
    type: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
) -> KnowledgeSearchResponse:
    try:
        return inspector.search(user.id, q, type_key=type, limit=limit)
    except KnowledgeInvalidId as exc:
        raise ApiHttpError(422, "INVALID_PAYLOAD", "Identificador inválido.") from exc


def _with_http_status(response: ApiMessageResponse) -> ApiMessageResponse | JSONResponse:
    if response.type.value != "error" or response.error is None:
        return response
    code = response.error.code
    http_status = 200
    if code == "PROVIDER_UNAVAILABLE":
        http_status = 503
    elif code == "INTERNAL":
        http_status = 500
    if http_status == 200:
        return response
    return JSONResponse(status_code=http_status, content=response.model_dump(mode="json"))
