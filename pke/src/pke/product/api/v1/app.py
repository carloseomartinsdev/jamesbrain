"""FastAPI app — fronteira HTTP pública."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pke.product.api.v1.dtos import ApiErrorBody
from pke.product.api.v1.errors import ApiErrorEnvelope, ApiHttpError
from pke.product.api.v1.routes import (
    get_auth_resolver,
    get_auth_service,
    get_knowledge_inspector,
    get_ontology,
    get_orchestrator,
    router,
)
from pke.product.knowledge.inspector import KnowledgeInspector
from pke.product.runtime import ProductRuntime


def create_app(runtime: ProductRuntime | None = None) -> FastAPI:
    runtime = runtime or ProductRuntime.from_env()
    app = FastAPI(title="PKE API", version="v1", docs_url=None, redoc_url=None)
    app.state.runtime = runtime

    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    def _orch():
        return runtime.orchestrator

    app.dependency_overrides[get_orchestrator] = _orch
    app.dependency_overrides[get_auth_resolver] = lambda: runtime.auth_resolver
    app.dependency_overrides[get_auth_service] = lambda: runtime.auth_service
    app.dependency_overrides[get_ontology] = lambda: runtime.ontology
    app.dependency_overrides[get_knowledge_inspector] = lambda: KnowledgeInspector(
        runtime.knowledge, runtime.ontology
    )
    app.include_router(router)

    @app.exception_handler(ApiHttpError)
    async def _api_error(_request: Request, exc: ApiHttpError) -> JSONResponse:
        body = ApiErrorEnvelope(
            error=ApiErrorBody(code=exc.code, message=exc.message, retryable=exc.retryable)
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        del exc
        body = ApiErrorEnvelope(
            error=ApiErrorBody(code="INVALID_PAYLOAD", message="Payload inválido.")
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    web_root = runtime.web_root
    if web_root.exists():
        _mount_web(app, web_root, debug_ui=runtime.debug_ui)
    return app


def _mount_web(app: FastAPI, web_root: Path, *, debug_ui: bool) -> None:
    index = web_root / "index.html"
    assets = web_root / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    def page() -> HTMLResponse:
        html = index.read_text(encoding="utf-8")
        flag = "true" if debug_ui else "false"
        html = html.replace("__PKE_DEBUG_UI__", flag)
        html = html.replace("__PKE_API_BASE_URL__", "/api/v1")
        return HTMLResponse(html)

    @app.get("/")
    def home() -> HTMLResponse:
        return page()

    @app.get("/login")
    def login_page() -> HTMLResponse:
        return page()

    @app.get("/settings")
    def settings() -> HTMLResponse:
        return page()

    @app.get("/c/{conversation_id}")
    def conversation(conversation_id: str) -> HTMLResponse:
        del conversation_id
        return page()
