"""Resolução determinística do PKE."""

from pke.resolution.context import PersonalContext, ResolutionContext, ResolutionPurpose
from pke.resolution.entities import (
    EntityResolution,
    EntityResolver,
    EvidenceKind,
    ResolutionCandidate,
    ResolutionConfidence,
    ResolutionStatus,
)
from pke.resolution.errors import (
    ContextIsolationError,
    EntityResolutionError,
    ForeignEntityError,
    ImpossibleTimeError,
    InsufficientTemporalContextError,
    InvalidTimezoneError,
    TemporalConflictError,
    TemporalError,
)
from pke.resolution.lookup import EntityLookup, InMemoryEntityLookup
from pke.resolution.normalize import normalize_lexical
from pke.resolution.query_temporal import (
    AbsoluteRange,
    QueryTemporalContext,
    QueryTemporalResolver,
    WeekStart,
)
from pke.resolution.temporal import TemporalContext, TemporalResolver

__all__ = [
    "ContextIsolationError",
    "EntityLookup",
    "EntityResolution",
    "EntityResolutionError",
    "EntityResolver",
    "EvidenceKind",
    "ForeignEntityError",
    "ImpossibleTimeError",
    "InMemoryEntityLookup",
    "InsufficientTemporalContextError",
    "InvalidTimezoneError",
    "AbsoluteRange",
    "PersonalContext",
    "QueryTemporalContext",
    "QueryTemporalResolver",
    "ResolutionCandidate",
    "ResolutionConfidence",
    "ResolutionContext",
    "ResolutionPurpose",
    "ResolutionStatus",
    "WeekStart",
    "TemporalConflictError",
    "TemporalContext",
    "TemporalError",
    "TemporalResolver",
    "normalize_lexical",
]
