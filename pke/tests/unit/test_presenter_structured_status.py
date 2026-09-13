from decimal import Decimal

from pke.application.ask_results import AskResult, AskStatus
from pke.product.conversation.presenter import render_query
from pke.product.conversation.result_projection import project_ask
from pke.query.results import CurrentRelationItem, MeasurementValueItem, QueryPlan, QueryResult
from pke.query.spec import AggregateKind, FactVersionPolicy, HierarchyMode, SortKey


def _plan() -> QueryPlan:
    return QueryPlan(
        sets=["relations"],
        filters={},
        expanded_event_type_ids=[],
        expanded_action_ids=[],
        version_policy=FactVersionPolicy.CURRENT,
        aggregation=AggregateKind.NONE,
        ordering=SortKey.EVENT_TIME_DESC,
        hierarchy=HierarchyMode.EXACT,
    )


def test_relation_yes_keeps_template_and_exposes_matched_name():
    result = QueryResult(
        matched_count=1,
        plan=_plan(),
        relation_answer="yes",
        current_relations=[
            CurrentRelationItem(
                relation_id="r1",
                relation_key="relation.owns",
                subject_entity_id="actor",
                object_entity_id="e-luna",
                is_current=True,
            )
        ],
    )
    text, data = render_query(
        result,
        entity_label=lambda _user, entity_id: "Luna" if entity_id == "e-luna" else None,
        user_id="u1",
    )
    assert text == "Sim."
    assert data is not None
    assert data["status"] == "answered"
    assert data["relation_answer"] == "yes"
    assert data["matched_entities"] == [{"canonical_name": "Luna"}]


def test_relation_false_stays_answered():
    result = QueryResult(
        matched_count=0,
        plan=_plan(),
        relation_answer="no",
    )
    text, data = render_query(result)
    assert data is not None
    assert data["status"] == "answered"
    assert data["kind"] == "relation"
    assert data["relation_answer"] == "no"
    assert "não" in text.casefold()
    assert data["status"] != "no_results"


def test_no_query_result_is_no_results_status():
    text, data = render_query(None)
    assert "ainda não sei" in text.casefold()
    assert data is not None
    assert data["status"] == "no_results"
    assert data["kind"] == "absence"


def test_measurement_weight_projects_value_and_unit():
    result = QueryResult(
        matched_count=1,
        plan=_plan(),
        measurement_status="known_single",
        measurement_dimension_key="weight",
        measurement_values=[
            MeasurementValueItem(numeric_value=Decimal("4"), unit="kg")
        ],
    )
    ask = AskResult(
        status=AskStatus.ANSWERED,
        raw_text="qual o peso da Luna?",
        query_result=result,
        resolved_entity_ids=["e-luna"],
    )
    text, data = project_ask(
        ask,
        entity_label=lambda _user, entity_id: "Luna" if entity_id == "e-luna" else None,
        user_id="u1",
    )
    assert data["status"] == "answered"
    assert data["kind"] == "measurement"
    assert data["value"] == "4"
    assert data["unit"] == "kg"
    assert data["dimension"] == "weight"
    assert "Luna" in text
    assert "4" in text
    assert "kg" in text
    assert data["status"] != "no_results"


def test_measurement_zero_is_not_absence():
    result = QueryResult(
        matched_count=1,
        plan=_plan(),
        measurement_status="known_single",
        measurement_dimension_key="temperature",
        measurement_values=[
            MeasurementValueItem(numeric_value=Decimal("0"), unit="°C")
        ],
    )
    ask = AskResult(
        status=AskStatus.ANSWERED,
        raw_text="qual a temperatura?",
        query_result=result,
        resolved_entity_ids=["e-luna"],
    )
    text, data = project_ask(
        ask,
        entity_label=lambda *_a: "Luna",
        user_id="u1",
    )
    assert data["status"] == "answered"
    assert data["kind"] == "measurement"
    assert data["value"] == "0"
    assert data["unit"] == "°C"
    assert "0" in text


def test_temporally_unknown_measurement_is_not_absence():
    result = QueryResult(
        matched_count=0,
        plan=_plan(),
        measurement_status="temporally_unknown",
        measurement_dimension_key="weight",
        measurement_values=[
            MeasurementValueItem(numeric_value=Decimal("4"), unit="kg")
        ],
    )
    ask = AskResult(
        status=AskStatus.ANSWERED,
        raw_text="qual o peso da Luna?",
        query_result=result,
        resolved_entity_ids=["e-luna"],
    )
    _, data = project_ask(
        ask,
        entity_label=lambda *_a: "Luna",
        user_id="u1",
    )
    assert data["status"] == "answered"
    assert data["kind"] == "measurement"
    assert data["value"] == "4"


def test_answered_without_scalar_does_not_become_absence():
    ask = AskResult(
        status=AskStatus.ANSWERED,
        raw_text="qual o peso da Luna?",
        query_result=QueryResult(matched_count=1, plan=_plan()),
        resolved_entity_ids=["e-luna"],
    )
    _, data = project_ask(ask, entity_label=lambda *_a: "Luna", user_id="u1")
    assert data["status"] == "answered"
    assert data.get("kind") != "absence"


def test_real_no_results_stays_absence():
    result = QueryResult(
        matched_count=0,
        plan=_plan(),
        measurement_status="unknown",
        measurement_dimension_key="height",
        measurement_values=[],
    )
    ask = AskResult(
        status=AskStatus.NO_RESULTS,
        raw_text="qual a altura da Luna?",
        query_result=result,
        resolved_entity_ids=["e-luna"],
    )
    text, data = project_ask(
        ask,
        entity_label=lambda *_a: "Luna",
        user_id="u1",
    )
    assert data["status"] == "no_results"
    assert data["kind"] == "absence"
    assert data["dimension"] == "height"
    assert "ainda não sei" in text.casefold()
    assert "Luna" in text

