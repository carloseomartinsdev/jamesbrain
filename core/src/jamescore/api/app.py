from __future__ import annotations

from fastapi import FastAPI

from jamescore.api.routes import router
from jamescore.application.orchestrator import Orchestrator
from jamescore.application.store import ConversationStore
from jamescore.capabilities.social import SocialCapability
from jamescore.clients.pke import PkeClient
from jamescore.presentation.presenter import ResponsePresenter
from jamescore.settings import Settings
from jamescore.tooling.registry import ToolRegistry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    store = ConversationStore(settings.db_path)
    orch = Orchestrator(
        store=store,
        pke=PkeClient(settings),
        social=SocialCapability(),
        tooling=ToolRegistry(),
        presenter=ResponsePresenter.from_settings(settings),
    )
    app = FastAPI(title="jamesCore", version="0.1.0")
    app.state.settings = settings
    app.state.orchestrator = orch
    app.include_router(router)
    return app
