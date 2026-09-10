"""Camada de interpretação — IR + contrato do Interpreter."""

from pke.interpretation.deepseek_interpreter import DeepSeekInterpreter
from pke.interpretation.envelope import LlmIrEnvelope
from pke.interpretation.interpreter import (
    FakeInterpreter,
    InterpretationContext,
    InterpretationError,
    Interpreter,
    ScriptedInterpreter,
)
from pke.interpretation.ontology_view import InterpreterOntologyView
from pke.interpretation.models import (
    CorrectionStrategy,
    EntityMention,
    IngestIntent,
    IngestIR,
    InterpretationResult,
    IrCorrection,
    IrEvent,
    IrFact,
    IrObligation,
    IrRelation,
    IrState,
    IrTime,
    MentionedEntity,
    MentionReferenceKind,
    RelationAssertionMode,
    IrQueryTime,
    QueryIR,
    QuerySpec,
    RelativePeriod,
)

__all__ = [
    "CorrectionStrategy",
    "DeepSeekInterpreter",
    "EntityMention",
    "FakeInterpreter",
    "InterpreterOntologyView",
    "LlmIrEnvelope",
    "IngestIR",
    "IngestIntent",
    "InterpretationContext",
    "InterpretationError",
    "InterpretationResult",
    "Interpreter",
    "IrCorrection",
    "IrEvent",
    "IrFact",
    "IrObligation",
    "IrRelation",
    "IrQueryTime",
    "IrState",
    "IrTime",
    "MentionedEntity",
    "MentionReferenceKind",
    "QueryIR",
    "QuerySpec",
    "RelationAssertionMode",
    "RelativePeriod",
    "ScriptedInterpreter",
]
