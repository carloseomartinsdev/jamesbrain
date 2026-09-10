"""Envelope discriminado para validar saída do LLM. Não altera IngestIR/QueryIR."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from pke.interpretation.models import IngestIR, InterpretationResult, QueryIR


class LlmIrEnvelope(BaseModel):
    """Discriminador explícito. Sem heurística `aggregate ⇒ QueryIR`."""

    model_config = ConfigDict(extra="forbid")

    ir_kind: Literal["ingest", "query"]
    ingest: IngestIR | None = None
    query: QueryIR | None = None

    @model_validator(mode="after")
    def _kind_matches_payload(self) -> LlmIrEnvelope:
        if self.ir_kind == "ingest":
            if self.ingest is None or self.query is not None:
                raise ValueError("ir_kind=ingest exige só o campo ingest")
        elif self.query is None or self.ingest is not None:
            raise ValueError("ir_kind=query exige só o campo query")
        return self

    def to_ir(self) -> InterpretationResult:
        if self.ir_kind == "ingest":
            assert self.ingest is not None
            return self.ingest
        assert self.query is not None
        return self.query


def interpretation_json_schema() -> dict:
    return LlmIrEnvelope.model_json_schema()
