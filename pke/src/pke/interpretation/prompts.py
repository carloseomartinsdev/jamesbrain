"""Dispatch de prompts versionados."""

from __future__ import annotations

from typing import Any

from pke.interpretation import prompts_v1, prompts_v2, prompts_v3, prompts_v4, prompts_v5
from pke.interpretation.interpreter import InterpretationContext
from pke.interpretation.ontology_view import InterpreterOntologyView
from pke.llm.models import LlmMessage

PROMPT_VERSION = prompts_v2.PROMPT_VERSION
PROMPT_VERSION_V1 = prompts_v1.PROMPT_VERSION
PROMPT_VERSION_V2 = prompts_v2.PROMPT_VERSION
PROMPT_VERSION_V3 = prompts_v3.PROMPT_VERSION
PROMPT_VERSION_V4 = prompts_v4.PROMPT_VERSION
PROMPT_VERSION_V5_EVENT = prompts_v5.PROMPT_VERSION

_VERSIONS = {
    PROMPT_VERSION_V1: prompts_v1,
    PROMPT_VERSION_V2: prompts_v2,
    PROMPT_VERSION_V3: prompts_v3,
    PROMPT_VERSION_V4: prompts_v4,
    PROMPT_VERSION_V5_EVENT: prompts_v5,
}


def resolve_prompt_module(version: str):
    if version not in _VERSIONS:
        raise ValueError(f"prompt version desconhecida: {version}")
    return _VERSIONS[version]


def build_messages(
    raw: str,
    ctx: InterpretationContext,
    ontology: InterpreterOntologyView,
    *,
    prompt_version: str = PROMPT_VERSION_V2,
    schema: dict[str, Any] | None = None,
) -> list[LlmMessage]:
    module = resolve_prompt_module(prompt_version)
    return module.build_messages(raw, ctx, ontology, schema=schema)
