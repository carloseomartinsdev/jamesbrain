from pke.application.ingest import ingest_result_from_interpretation_error
from pke.application.results import IngestStatus
from pke.interpretation.interpreter import InterpretationError


def test_execution_incomplete_maps_to_clarification() -> None:
    r = ingest_result_from_interpretation_error(
        "medi a temperatura e deu 95°C",
        InterpretationError("semantic_resolution:execution_incomplete:missing_entity"),
    )
    assert r is not None
    assert r.status is IngestStatus.NEEDS_CLARIFICATION
    assert r.materialization is None
    assert r.clarification is not None
    assert r.clarification.blocking is True


def test_generic_concept_resolution_not_mapped() -> None:
    r = ingest_result_from_interpretation_error(
        "x",
        InterpretationError("semantic_resolution:concept_resolution"),
    )
    assert r is None
