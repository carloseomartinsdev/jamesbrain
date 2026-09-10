"""Validação semântica — o que foi informado faz sentido?"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from pke.domain.ontology import ConceptKind
from pke.domain.value_objects import EpistemicStatus, Qualifier, SourceKind, TimePrecision
from pke.interpretation.models import (
    CorrectionStrategy,
    IngestIntent,
    IrFact,
    MentionReferenceKind,
)
from pke.ontology.errors import ConceptKindError, ConceptNotFoundError
from pke.ontology.registry import OntologyRegistry
from pke.reasoning.candidate import KnowledgeCandidate
from pke.reasoning.issues import Issue, Severity
from pke.resolution.entities import ResolutionStatus
from pke.resolution.lookup import EntityLookup


class ValidationResult:
    def __init__(self) -> None:
        self.errors: list[Issue] = []
        self.warnings: list[Issue] = []
        self.checked_rules: list[str] = []

    @property
    def valid(self) -> bool:
        return not self.errors

    def add(self, issue: Issue) -> None:
        if issue.severity is Severity.ERROR:
            self.errors.append(issue)
        else:
            self.warnings.append(issue)


class KnowledgeValidator:
    def __init__(self, ontology: OntologyRegistry, lookup: EntityLookup) -> None:
        self._ontology = ontology
        self._lookup = lookup

    def validate(self, candidate: KnowledgeCandidate) -> ValidationResult:
        result = ValidationResult()
        self._ontology_refs(candidate, result)
        self._entities(candidate, result)
        self._time(candidate, result)
        self._epistemic(candidate, result)
        self._values(candidate, result)
        return result

    def _check(self, result: ValidationResult, rule_id: str) -> None:
        if rule_id not in result.checked_rules:
            result.checked_rules.append(rule_id)

    def _err(
        self,
        result: ValidationResult,
        rule_id: str,
        code: str,
        message: str,
        **kwargs: str | None,
    ) -> None:
        self._check(result, rule_id)
        result.add(
            Issue(
                code=code,
                rule_id=rule_id,
                message=message,
                severity=Severity.ERROR,
                field=kwargs.get("field"),
                concept_key=kwargs.get("concept_key"),
            )
        )

    def _warn(
        self,
        result: ValidationResult,
        rule_id: str,
        code: str,
        message: str,
        **kwargs: str | None,
    ) -> None:
        self._check(result, rule_id)
        result.add(
            Issue(
                code=code,
                rule_id=rule_id,
                message=message,
                severity=Severity.WARNING,
                field=kwargs.get("field"),
                concept_key=kwargs.get("concept_key"),
            )
        )

    def _ontology_refs(self, candidate: KnowledgeCandidate, result: ValidationResult) -> None:
        rule = "ontology.refs"
        ir = candidate.ir
        refs: list[tuple[str, object]] = []
        if ir.event:
            refs.append(("event.type", ir.event.type))
            if ir.event.action:
                refs.append(("event.action", ir.event.action))
        if ir.state:
            refs.append(("state.value", ir.state.value))
            if ir.state.dimension:
                refs.append(("state.dimension", ir.state.dimension))
        if ir.relation:
            refs.append(("relation.type", ir.relation.type))
        if ir.obligation:
            refs.append(("obligation.type", ir.obligation.type))
        for fact in _facts(candidate):
            refs.append(("fact.attribute", fact.attribute))
        for binding in candidate.bindings:
            if binding.mention.type_hint:
                refs.append(("mention.type_hint", binding.mention.type_hint))
        for field, ref in refs:
            try:
                resolved = self._ontology.resolve_ref(ref)  # type: ignore[arg-type]
            except (ConceptNotFoundError, ConceptKindError) as exc:
                self._err(result, rule, "ontology.unknown_or_incompatible", str(exc), field=field)
                continue
            self._check(result, rule)
            concept = self._ontology.get_by_id(resolved.concept_id or "")
            if concept is None:
                self._err(result, rule, "ontology.unknown", "conceito inexistente", field=field)
                continue
            if field.endswith("action") and concept.kind is not ConceptKind.ACTION:
                self._err(
                    result,
                    "ontology.action_kind",
                    "ontology.kind_mismatch",
                    "ação deve ser kind=action",
                    field=field,
                    concept_key=concept.key,
                )
            elif field.startswith("fact") and concept.kind is not ConceptKind.ATTRIBUTE:
                self._err(
                    result,
                    "ontology.attribute_kind",
                    "ontology.kind_mismatch",
                    "fact deve apontar para attribute",
                    field=field,
                    concept_key=concept.key,
                )
            elif field.startswith("state.value") and concept.kind is not ConceptKind.STATE_VALUE:
                self._err(
                    result,
                    "ontology.state_value_kind",
                    "ontology.kind_mismatch",
                    "state value deve ser kind=state_value",
                    field=field,
                    concept_key=concept.key,
                )
            elif field.startswith("state.dimension") and concept.kind is not ConceptKind.STATE_DIMENSION:
                self._err(
                    result,
                    "ontology.state_dimension_kind",
                    "ontology.kind_mismatch",
                    "state dimension deve ser kind=state_dimension",
                    field=field,
                    concept_key=concept.key,
                )
            elif field.startswith("relation.") and concept.kind is not ConceptKind.RELATION_TYPE:
                self._err(
                    result,
                    "ontology.relation_type_kind",
                    "ontology.kind_mismatch",
                    "relation deve ser kind=relation_type",
                    field=field,
                    concept_key=concept.key,
                )
            else:
                self._check(result, "ontology.action_kind")
                self._check(result, "ontology.attribute_kind")

    def _entities(self, candidate: KnowledgeCandidate, result: ValidationResult) -> None:
        rule = "entity.bindings"
        self._check(result, rule)
        for binding in candidate.bindings:
            status = binding.resolution.status
            if status is ResolutionStatus.AMBIGUOUS:
                self._err(
                    result,
                    rule,
                    "entity.ambiguous",
                    "menção ambígua não é persistível",
                    field=binding.mention.text,
                )
            if status is ResolutionStatus.CREATE_CANDIDATE:
                if binding.mention.reference_kind in {
                    MentionReferenceKind.CONTEXTUAL,
                    MentionReferenceKind.POSSESSIVE,
                }:
                    if self._allow_contextual_vehicle_create(binding):
                        self._check(result, "entity.create_candidate")
                        self._warn(
                            result,
                            "entity.create_candidate",
                            "entity.create_pending",
                            "veículo contextual será criado no commit (E1.2 ownership)",
                            field=binding.mention.text,
                        )
                    else:
                        self._err(
                            result,
                            "entity.create_candidate",
                            "entity.create_not_allowed",
                            "create_candidate inválido para referência contextual",
                        )
                elif candidate.ir.intent is IngestIntent.CORRECT:
                    self._err(
                        result,
                        "entity.create_candidate",
                        "entity.create_not_allowed",
                        "correção não cria entidade",
                    )
                else:
                    self._check(result, "entity.create_candidate")
                    self._warn(
                        result,
                        "entity.create_candidate",
                        "entity.create_pending",
                        "entidade será criada no commit",
                        field=binding.mention.text,
                    )
            if status is ResolutionStatus.UNRESOLVED:
                if binding.mention.reference_kind in {
                    MentionReferenceKind.CONTEXTUAL,
                    MentionReferenceKind.POSSESSIVE,
                }:
                    self._err(
                        result,
                        "entity.contextual_unresolved",
                        "entity.contextual_unresolved",
                        "referência contextual essencial não resolvida",
                        field=binding.mention.text,
                    )
            if binding.resolution.entity_id:
                entity = self._lookup.get_by_id(binding.resolution.entity_id, candidate.user_id)
                if entity is None:
                    self._err(
                        result,
                        "entity.isolation",
                        "entity.foreign",
                        "entidade não pertence ao usuário",
                        field=binding.resolution.entity_id,
                    )
                else:
                    self._check(result, "entity.isolation")

    def _allow_contextual_vehicle_create(self, binding) -> bool:
        """E1.2: first 'meu carro' may CREATE vehicle Entity (then relation.owns)."""
        from pke.ontology.seeds import core_concept_id
        from pke.reasoning.candidate import MentionBinding

        assert isinstance(binding, MentionBinding)
        type_id = binding.resolution.create_type_id
        if type_id is None:
            return False
        vehicle_id = core_concept_id("entity.vehicle")
        if type_id == vehicle_id:
            return True
        return self._ontology.is_descendant_of(type_id, vehicle_id)

    def _time(self, candidate: KnowledgeCandidate, result: ValidationResult) -> None:
        ir = candidate.ir
        if ir.event is not None:
            self._check(result, "time.event_resolved")
            if not candidate.has_persistable_temporal():
                self._err(result, "time.event_resolved", "time.missing", "evento exige tempo persistível")
            elif candidate.resolved_time is not None:
                ir_prec = ir.event.time.precision
                got = candidate.resolved_time.precision
                if (
                    ir_prec is TimePrecision.DAY
                    and got is TimePrecision.MINUTE
                    and ir.event.time.time_of_day is None
                    and ir.event.time.instant is None
                ):
                    self._err(
                        result,
                        "time.precision_not_promoted",
                        "time.precision_promoted",
                        "precisão parcial promovida indevidamente",
                    )
                else:
                    self._check(result, "time.precision_not_promoted")
            else:
                self._check(result, "time.precision_not_promoted")
        if ir.state is not None:
            self._check(result, "time.state_resolved")
            if not candidate.has_persistable_temporal():
                self._err(result, "time.state_resolved", "time.missing", "state exige tempo persistível")
        if ir.relation is not None:
            self._check(result, "time.relation_resolved")
            if not candidate.has_persistable_temporal():
                self._err(
                    result,
                    "time.relation_resolved",
                    "time.missing",
                    "relation exige tempo persistível",
                )
        if ir.obligation is not None:
            self._check(result, "time.recurrence")
            rec = ir.obligation.cadence
            if rec.freq == "monthly" and rec.by_monthday is None:
                self._err(
                    result,
                    "time.recurrence",
                    "time.recurrence_incompatible",
                    "monthly exige by_monthday",
                )
            if rec.freq not in {"monthly"} and ir.obligation.type.key == "event.recurring_bill":
                self._err(
                    result,
                    "time.recurrence",
                    "time.recurrence_incompatible",
                    "recorrência incompatível com recurring_bill",
                )

    def _epistemic(self, candidate: KnowledgeCandidate, result: ValidationResult) -> None:
        self._check(result, "epistemic.approx_not_exact")
        self._check(result, "epistemic.confidence")
        self._check(result, "epistemic.inference_source")
        self._check(result, "epistemic.correction_target")
        for fact in _facts(candidate):
            if (
                fact.qualifier is Qualifier.EXACT
                and fact.epistemic_status is EpistemicStatus.UNCERTAIN
            ):
                self._err(
                    result,
                    "epistemic.approx_not_exact",
                    "epistemic.exact_vs_uncertain",
                    "qualifier exact incompatível com incerteza",
                    concept_key=fact.attribute.key,
                )
            if fact.qualifier is Qualifier.APPROXIMATELY and fact.confidence >= 0.99:
                self._err(
                    result,
                    "epistemic.confidence",
                    "epistemic.confidence_inflated",
                    "confiança aumentada sem regra",
                    concept_key=fact.attribute.key,
                )
            if (
                fact.epistemic_status is EpistemicStatus.INFERRED
                and candidate.source_kind is not SourceKind.INFERENCE
            ):
                self._err(
                    result,
                    "epistemic.inference_source",
                    "epistemic.inference_source",
                    "inferência exige source inference",
                )
        corr = candidate.ir.correction
        if corr is not None:
            if corr.strategy is CorrectionStrategy.LAST_EVENT and not (
                corr.event_id or corr.fact_id
            ):
                self._err(
                    result,
                    "epistemic.correction_target",
                    "correction.target_unresolved",
                    "correção sem alvo concreto",
                )
            elif not (corr.event_id or corr.fact_id):
                self._err(
                    result,
                    "epistemic.correction_target",
                    "correction.target_unresolved",
                    "correção sem alvo concreto",
                )

    def _values(self, candidate: KnowledgeCandidate, result: ValidationResult) -> None:
        self._check(result, "value.money")
        for fact in _facts(candidate):
            if fact.attribute.key != "attribute.amount":
                continue
            amount, currency, ok = _parse_money(fact.value)
            if not ok:
                self._err(
                    result,
                    "value.money",
                    "value.money_invalid",
                    "valor monetário inválido",
                    concept_key=fact.attribute.key,
                )
                continue
            if currency is None:
                self._err(
                    result,
                    "value.money",
                    "value.money_currency_missing",
                    "Money exige currency",
                    concept_key=fact.attribute.key,
                )
            if amount is not None and amount < 0:
                self._err(
                    result,
                    "value.money",
                    "value.amount_negative",
                    "valor monetário impossível",
                    concept_key=fact.attribute.key,
                )


def _facts(candidate: KnowledgeCandidate) -> list[IrFact]:
    ir = candidate.ir
    if ir.event:
        return list(ir.event.facts)
    if ir.obligation:
        return list(ir.obligation.facts)
    if ir.correction:
        return list(ir.correction.facts)
    return []


def _parse_money(value: object) -> tuple[Decimal | None, str | None, bool]:
    if isinstance(value, dict):
        raw = value.get("amount")
        currency = value.get("currency")
        if raw is None:
            return None, str(currency) if currency else None, False
        try:
            return Decimal(str(raw)), str(currency) if currency else None, True
        except InvalidOperation:
            return None, str(currency) if currency else None, False
    if hasattr(value, "amount") and hasattr(value, "currency"):
        return Decimal(str(value.amount)), str(value.currency), True
    try:
        return Decimal(str(value)), None, True
    except InvalidOperation:
        return None, None, False
