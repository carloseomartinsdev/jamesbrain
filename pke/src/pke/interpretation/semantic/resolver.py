"""SemanticConceptResolver — expression + role + context → canonical concept."""

from __future__ import annotations

from pke.interpretation.semantic.aliases import (
    SEMANTIC_ALIASES,
    collect_expressions,
    normalize_expression,
)
from pke.interpretation.semantic.models import (
    PrimitiveKind,
    ResolutionConfidence,
    ResolutionProvenance,
    ResolutionStatus,
    ResolvedConcepts,
    SemanticProposal,
)
from pke.interpretation.semantic.sense import (
    SemanticSense,
    primary_surface_expression,
    recognize_senses,
)
from pke.interpretation.transport.catalog import ConceptCatalog


def _subject_kind(proposal: SemanticProposal) -> str | None:
    if proposal.subject and proposal.subject.kind_hint:
        return proposal.subject.kind_hint
    for ent in proposal.entities_mentioned:
        if ent.kind_hint:
            return ent.kind_hint
    return None


def _object_kind(proposal: SemanticProposal) -> str | None:
    if proposal.object and proposal.object.kind_hint:
        return proposal.object.kind_hint
    return None


def _constraints_match(proposal: SemanticProposal, alias) -> bool:
    c = alias.constraints
    subj = _subject_kind(proposal)
    obj = _object_kind(proposal)
    if c.subject_kinds and (subj is None or subj not in c.subject_kinds):
        return False
    if c.object_kinds and (obj is None or obj not in c.object_kinds):
        return False
    if c.require_change_semantics and not proposal.change_semantics:
        return False
    if c.require_condition_semantics and not proposal.condition_semantics:
        return False
    if c.require_link_semantics and not proposal.link_semantics:
        return False
    if c.require_stable_property and not proposal.stable_property_semantics:
        return False
    if c.require_event_context and not (
        proposal.change_semantics or proposal.action_expression or proposal.event_expression
    ):
        return False
    exprs = collect_expressions(proposal)
    raw_blob = " ".join(exprs)
    for forbidden in c.forbid_if_expressions:
        fn = normalize_expression(forbidden)
        if fn in raw_blob:
            return False
    return True


def _alias_matches(proposal: SemanticProposal, alias, exprs: list[str]) -> bool:
    blob = " ".join(exprs)
    if alias.primitive is PrimitiveKind.UNKNOWN:
        return any(normalize_expression(a) in blob for a in alias.expressions)
    if not _constraints_match(proposal, alias):
        return False
    return any(a in blob for a in alias.expressions)


def _owns_alias_preempted_by_structured_relation(proposal, alias, primitive: PrimitiveKind) -> bool:
    """Structured relation_expression outranks raw-text owns cues ('é meu' in the utterance)."""
    if primitive is not PrimitiveKind.RELATION:
        return False
    if getattr(alias, "canonical_key", None) != "relation.owns":
        return False
    structured = normalize_expression(proposal.relation_expression or "")
    if not structured:
        return False
    owns_tokens = {normalize_expression(e) for e in alias.expressions}
    return structured not in owns_tokens


def _alias_sort_key(alias) -> tuple:
    """Deterministic tie-break — registry insertion order must not decide semantics."""
    expr_key = min(alias.expressions) if alias.expressions else ""
    canon = alias.canonical_key or alias.action_key or alias.value_key or alias.event_type_key or ""
    return (-alias.priority, expr_key, canon)


def _canonicalization_gate(
    proposal: SemanticProposal,
    alias,
    senses: frozenset[SemanticSense],
) -> tuple[bool, str | None]:
    if alias.action_key == "action.replace":
        if SemanticSense.INSTALL in senses:
            return False, "install sense — not action.replace"
        if SemanticSense.EXCHANGE_IDEA in senses:
            return False, "exchange idea — not physical replace"
        if SemanticSense.CURRENCY_EXCHANGE in senses:
            return False, "currency exchange — not action.replace"
        if SemanticSense.CLOTHING_CHANGE in senses:
            return False, "clothing change — not component replace"
        if SemanticSense.REPLACE_PHYSICAL not in senses:
            return False, "replace requires physical component evidence"

    if alias.action_key == "action.install":
        if SemanticSense.FACILITIES in senses:
            return False, "facilities sense — not action.install"
        if SemanticSense.INSTALL not in senses:
            return False, "install action requires install sense"
        if SemanticSense.REPLACE_PHYSICAL in senses and SemanticSense.INSTALL not in senses:
            return False, "physical replace — not install"

    if alias.value_key == "state.value.working":
        if SemanticSense.PROPERTY_NEW in senses:
            return False, "property new — not operational working"
        if SemanticSense.FACILITIES in senses:
            return False, "facilities sense — not operational condition"

    if alias.value_key == "state.value.broken":
        if SemanticSense.PROPERTY_NEW in senses:
            return False, "property new — not broken"
        if SemanticSense.OPERATIONAL_BROKEN not in senses:
            subj = _subject_kind(proposal)
            if subj not in {"appliance", "thing", "vehicle"}:
                return False, "broken requires operational condition context"

    if alias.value_key == "state.value.open":
        if SemanticSense.PROPERTY_NEW in senses:
            return False, "property new — not openness open"

    if alias.canonical_key == "relation.employed_by":
        subj = _subject_kind(proposal)
        if subj in {"thing", "appliance", "vehicle"}:
            return False, "employment requires person subject"
        obj = _object_kind(proposal)
        if obj is not None and obj != "organization":
            return False, "employment requires organization object"

    return True, None


def _primary_recognized_sense(senses: frozenset[SemanticSense]) -> str | None:
    priority = (
        SemanticSense.EXCHANGE_IDEA,
        SemanticSense.CLOTHING_CHANGE,
        SemanticSense.CURRENCY_EXCHANGE,
        SemanticSense.INSTALL,
        SemanticSense.FACILITIES,
        SemanticSense.AMBIGUOUS_PASS,
        SemanticSense.REPLACE_PHYSICAL,
        SemanticSense.PROPERTY_NEW,
    )
    for sense in priority:
        if sense in senses:
            return sense.value
    return None


def _ontology_gap_result(
    proposal: SemanticProposal,
    primitive: PrimitiveKind,
    senses: frozenset[SemanticSense],
) -> ResolvedConcepts | None:
    surface = primary_surface_expression(proposal)
    if SemanticSense.INSTALL in senses and primitive is PrimitiveKind.EVENT:
        if "action.install" in ConceptCatalog.actions:
            return None
        return ResolvedConcepts(
            primitive=primitive,
            confidence=ResolutionConfidence.CONTEXTUAL,
            provenance=ResolutionProvenance.SEMANTIC,
            unresolved=True,
            resolution_status=ResolutionStatus.ONTOLOGY_GAP,
            recognized_sense=SemanticSense.INSTALL.value,
            surface_expression=surface,
            ontology_gap=True,
            safe_abstention=True,
            abstention_reason="semantic sense recognized; no compatible canonical action",
            notes=["install sense — action.install absent from CORE"],
        )
    if SemanticSense.FACILITIES in senses and SemanticSense.PROPERTY_NEW in senses:
        status = ResolutionStatus.SAFE_PARTIAL
        if primitive is PrimitiveKind.ATTRIBUTE:
            status = ResolutionStatus.ONTOLOGY_GAP
        return ResolvedConcepts(
            primitive=primitive,
            confidence=ResolutionConfidence.CONTEXTUAL,
            provenance=ResolutionProvenance.SEMANTIC,
            unresolved=True,
            resolution_status=status,
            recognized_sense=SemanticSense.FACILITIES.value,
            surface_expression=surface,
            ontology_gap=True,
            safe_abstention=True,
            abstention_reason="facilities/premises sense; no canonical concept in CORE",
            notes=["facilities sense — no canonical attribute/state concept"],
        )
    if SemanticSense.CURRENCY_EXCHANGE in senses:
        return ResolvedConcepts(
            primitive=primitive,
            confidence=ResolutionConfidence.UNRESOLVED,
            provenance=ResolutionProvenance.SEMANTIC,
            unresolved=True,
            resolution_status=ResolutionStatus.ONTOLOGY_GAP,
            recognized_sense=SemanticSense.CURRENCY_EXCHANGE.value,
            surface_expression=surface,
            ontology_gap=True,
            safe_abstention=True,
            abstention_reason="currency exchange sense; no canonical concept in CORE",
            notes=["currency exchange — no canonical concept"],
        )
    if SemanticSense.CLOTHING_CHANGE in senses:
        return ResolvedConcepts(
            primitive=primitive,
            confidence=ResolutionConfidence.UNRESOLVED,
            provenance=ResolutionProvenance.SEMANTIC,
            unresolved=True,
            resolution_status=ResolutionStatus.UNRESOLVED,
            recognized_sense=SemanticSense.CLOTHING_CHANGE.value,
            surface_expression=surface,
            safe_abstention=True,
            abstention_reason="clothing change — not physical component replace",
            notes=["clothing change — no safe canonical action"],
        )
    if SemanticSense.EXCHANGE_IDEA in senses:
        return ResolvedConcepts(
            primitive=primitive,
            confidence=ResolutionConfidence.UNRESOLVED,
            provenance=ResolutionProvenance.SEMANTIC,
            unresolved=True,
            resolution_status=ResolutionStatus.BLOCKED,
            recognized_sense=SemanticSense.EXCHANGE_IDEA.value,
            surface_expression=surface,
            safe_abstention=True,
            abstention_reason="exchange idea — not physical replace",
            notes=["exchange idea — blocked from action.replace"],
        )
    if SemanticSense.AMBIGUOUS_PASS in senses:
        return ResolvedConcepts(
            primitive=primitive,
            confidence=ResolutionConfidence.AMBIGUOUS,
            provenance=ResolutionProvenance.SEMANTIC,
            unresolved=True,
            resolution_status=ResolutionStatus.AMBIGUOUS,
            recognized_sense=SemanticSense.AMBIGUOUS_PASS.value,
            surface_expression=surface,
            safe_abstention=True,
            abstention_reason="ambiguous pass — insufficient context",
            notes=["ambiguous pass without shopping/place context"],
        )
    return None


def _learned_relation_result(
    proposal: SemanticProposal,
    primitive: PrimitiveKind,
    senses: frozenset[SemanticSense],
    surface: str | None,
) -> ResolvedConcepts | None:
    """Complete link with no CORE alias → persistable EXTENDED relation type.

    Does not invent Attribute dimensions. Requires subject + object + expression.
    """
    if primitive is not PrimitiveKind.RELATION:
        return None
    expr = (proposal.relation_expression or "").strip()
    if not expr or proposal.subject is None or proposal.object is None:
        return None
    from pke.interpretation.semantic.learned_relation import (
        learned_key_from_expression,
        publish_relation_type,
    )

    key = learned_key_from_expression(expr)
    if key is None:
        return None
    publish_relation_type(key)
    return ResolvedConcepts(
        primitive=primitive,
        relation_type=key,
        confidence=ResolutionConfidence.CONTEXTUAL,
        provenance=ResolutionProvenance.SEMANTIC,
        unresolved=False,
        resolution_status=ResolutionStatus.RESOLVED,
        recognized_sense=_primary_recognized_sense(senses),
        surface_expression=surface,
        notes=[f"learned relation type={key}"],
    )


def _publish_trained_alias(alias) -> None:
    """EXTENDED trained keys are not in a CORE-only ConceptCatalog until published."""
    from pke.ontology.trained import is_trained_extended_key

    if alias.canonical_key and is_trained_extended_key(alias.canonical_key):
        ConceptCatalog.relation_types.add(alias.canonical_key)
    if alias.action_key and is_trained_extended_key(alias.action_key):
        ConceptCatalog.actions.add(alias.action_key)
    if alias.event_type_key and is_trained_extended_key(alias.event_type_key):
        ConceptCatalog.event_types.add(alias.event_type_key)


def _validate_keys(concepts: ResolvedConcepts) -> ResolvedConcepts:
    notes = list(concepts.notes)
    unresolved = concepts.unresolved
    status = concepts.resolution_status

    if concepts.relation_type and concepts.relation_type not in ConceptCatalog.relation_types:
        notes.append(f"unknown relation {concepts.relation_type}")
        concepts = concepts.model_copy(update={"relation_type": None, "unresolved": True})
        unresolved = True
    if concepts.state_value and concepts.state_value not in ConceptCatalog.state_values:
        notes.append(f"unknown state value {concepts.state_value}")
        concepts = concepts.model_copy(update={"state_value": None, "unresolved": True})
        unresolved = True
    if concepts.state_dimension and concepts.state_dimension not in ConceptCatalog.state_dimensions:
        notes.append(f"unknown dimension {concepts.state_dimension}")
        concepts = concepts.model_copy(update={"state_dimension": None, "unresolved": True})
        unresolved = True
    if concepts.action and concepts.action not in ConceptCatalog.actions:
        notes.append(f"unknown action {concepts.action}")
        concepts = concepts.model_copy(update={"action": None, "unresolved": True})
        unresolved = True
    if concepts.event_type and concepts.event_type not in ConceptCatalog.event_types:
        notes.append(f"unknown event type {concepts.event_type}")
        concepts = concepts.model_copy(update={"event_type": None, "unresolved": True})
        unresolved = True
    if concepts.attribute and concepts.attribute not in ConceptCatalog.attributes:
        notes.append(f"unknown attribute {concepts.attribute}")
        concepts = concepts.model_copy(update={"attribute": None, "unresolved": True})
        unresolved = True

    if unresolved and status is ResolutionStatus.UNRESOLVED:
        status = ResolutionStatus.UNRESOLVED
    elif unresolved and status is ResolutionStatus.RESOLVED:
        status = ResolutionStatus.UNRESOLVED

    updates: dict = {"notes": notes}
    if unresolved != concepts.unresolved:
        updates["unresolved"] = unresolved
    if status != concepts.resolution_status:
        updates["resolution_status"] = status
    if updates != {"notes": notes} or notes != concepts.notes:
        concepts = concepts.model_copy(update=updates)
    elif notes != concepts.notes:
        concepts = concepts.model_copy(update={"notes": notes})
    return concepts


def resolve_concepts(proposal: SemanticProposal, primitive: PrimitiveKind) -> ResolvedConcepts:
    exprs = collect_expressions(proposal)
    senses = recognize_senses(proposal)
    surface = primary_surface_expression(proposal)

    if primitive is PrimitiveKind.TYPE:
        return ResolvedConcepts(
            primitive=PrimitiveKind.TYPE,
            confidence=ResolutionConfidence.CONTEXTUAL,
            provenance=ResolutionProvenance.SEMANTIC,
            unresolved=True,
            resolution_status=ResolutionStatus.SAFE_PARTIAL,
            recognized_sense=SemanticSense.CLASSIFICATION.value,
            surface_expression=surface,
            safe_abstention=True,
            abstention_reason="classification recognized — not Attribute; type write path deferred",
            notes=["classification — blocked from Attribute materialization path"],
        )

    if primitive is PrimitiveKind.ATTRIBUTE:
        from pke.interpretation.semantic.attribute_resolution import (
            resolve_attribute_value,
            resolve_companion_attribute_values,
        )
        from pke.interpretation.semantic.models import AttributeValueSlot

        gap = _ontology_gap_result(proposal, primitive, senses)
        if gap is not None:
            return gap

        attr = resolve_attribute_value(proposal)
        companions = resolve_companion_attribute_values(proposal)
        if attr is None and companions:
            attr = companions[0]
        if attr is None:
            return ResolvedConcepts(
                primitive=primitive,
                confidence=ResolutionConfidence.UNRESOLVED,
                provenance=ResolutionProvenance.SEMANTIC,
                unresolved=True,
                resolution_status=ResolutionStatus.UNRESOLVED,
                recognized_sense=_primary_recognized_sense(senses),
                surface_expression=surface,
                safe_abstention=True,
                abstention_reason="attribute dimension/value not safely determined",
                notes=["attribute — no safe dimension/value"],
            )
        companion_slots: list[AttributeValueSlot] = []
        for c in companions:
            if c.dimension_key == attr.dimension_key:
                continue
            companion_slots.append(
                AttributeValueSlot(
                    dimension_key=c.dimension_key,
                    value_kind=c.value_kind.value,
                    text_value=c.text_value,
                    numeric_value=(
                        format(c.numeric_value, "f") if c.numeric_value is not None else None
                    ),
                    unit=c.unit,
                    year_value=c.year_value,
                    is_current=c.is_current,
                )
            )
        notes = [f"attribute dimension={attr.dimension_key} kind={attr.value_kind.value}"]
        if companion_slots:
            notes.append(
                "companions=" + ",".join(s.dimension_key for s in companion_slots)
            )
        return ResolvedConcepts(
            primitive=primitive,
            confidence=ResolutionConfidence.CONTEXTUAL,
            provenance=ResolutionProvenance.SEMANTIC,
            unresolved=False,
            resolution_status=ResolutionStatus.RESOLVED,
            attribute_dimension_key=attr.dimension_key,
            attribute_value_kind=attr.value_kind.value,
            attribute_text_value=attr.text_value,
            attribute_numeric_value=(
                format(attr.numeric_value, "f") if attr.numeric_value is not None else None
            ),
            attribute_unit=attr.unit,
            attribute_year_value=attr.year_value,
            attribute_is_current=attr.is_current,
            attribute_companions=companion_slots,
            recognized_sense=_primary_recognized_sense(senses),
            surface_expression=surface,
            notes=notes,
        )

    if primitive is PrimitiveKind.MEASUREMENT:
        from pke.interpretation.semantic.measurement_resolution import resolve_measurement_value

        measured = resolve_measurement_value(proposal)
        if measured is None:
            return ResolvedConcepts(
                primitive=primitive,
                confidence=ResolutionConfidence.UNRESOLVED,
                provenance=ResolutionProvenance.SEMANTIC,
                unresolved=True,
                resolution_status=ResolutionStatus.SAFE_PARTIAL,
                recognized_sense="measurement",
                surface_expression=surface,
                safe_abstention=True,
                abstention_reason="measurement dimension/value incomplete or storage deferred",
                notes=["measurement — awaiting structured dimension/value and/or schema v9"],
                measurement_dimension_key=proposal.measurable_dimension_key,
                measurement_numeric_value=proposal.measurement_numeric_value,
                measurement_unit=proposal.measurement_unit,
                measurement_currency_code=proposal.measurement_currency_code,
            )
        return ResolvedConcepts(
            primitive=primitive,
            confidence=ResolutionConfidence.CONTEXTUAL,
            provenance=ResolutionProvenance.SEMANTIC,
            unresolved=False,
            resolution_status=ResolutionStatus.RESOLVED,
            recognized_sense="measurement",
            surface_expression=surface,
            measurement_dimension_key=measured.dimension_key,
            measurement_numeric_value=format(measured.numeric_value, "f"),
            measurement_unit=measured.unit,
            measurement_currency_code=measured.currency_code,
            notes=[f"measurement dimension={measured.dimension_key}"],
        )

    matches: list[tuple[tuple, object]] = []
    blocked_reasons: list[str] = []

    from pke.ontology.trained import trained_aliases

    for alias in (*SEMANTIC_ALIASES, *trained_aliases()):
        if alias.primitive is PrimitiveKind.UNKNOWN:
            if _alias_matches(proposal, alias, exprs):
                return ResolvedConcepts(
                    primitive=primitive,
                    confidence=ResolutionConfidence.UNRESOLVED,
                    provenance=ResolutionProvenance.SEMANTIC,
                    unresolved=True,
                    resolution_status=ResolutionStatus.BLOCKED,
                    recognized_sense=_primary_recognized_sense(senses),
                    surface_expression=surface,
                    safe_abstention=True,
                    abstention_reason="blocked alias — not canonicalizable",
                    notes=["blocked alias — not canonicalizable"],
                )
            continue
        if alias.primitive != primitive:
            continue
        if _owns_alias_preempted_by_structured_relation(proposal, alias, primitive):
            continue
        if not _alias_matches(proposal, alias, exprs):
            continue
        allowed, reason = _canonicalization_gate(proposal, alias, senses)
        if not allowed:
            blocked_reasons.append(reason or "canonicalization gate blocked")
            continue
        matches.append((_alias_sort_key(alias), alias))

    if not matches:
        gap = _ontology_gap_result(proposal, primitive, senses)
        if gap is not None:
            return gap
        learned = _learned_relation_result(proposal, primitive, senses, surface)
        if learned is not None:
            return learned
        notes = blocked_reasons or ["no alias match"]
        abstention = blocked_reasons[0] if blocked_reasons else "no compatible canonical concept"
        return ResolvedConcepts(
            primitive=primitive,
            confidence=ResolutionConfidence.UNRESOLVED,
            provenance=ResolutionProvenance.SEMANTIC,
            unresolved=True,
            resolution_status=ResolutionStatus.UNRESOLVED,
            recognized_sense=_primary_recognized_sense(senses),
            surface_expression=surface,
            safe_abstention=bool(blocked_reasons),
            abstention_reason=abstention,
            notes=notes,
        )

    matches.sort(key=lambda item: item[0])
    if len(matches) > 1 and matches[0][0] == matches[1][0]:
        return ResolvedConcepts(
            primitive=primitive,
            confidence=ResolutionConfidence.AMBIGUOUS,
            provenance=ResolutionProvenance.CONTEXTUAL,
            unresolved=True,
            resolution_status=ResolutionStatus.AMBIGUOUS,
            surface_expression=surface,
            safe_abstention=True,
            abstention_reason="multiple alias candidates with equal evidence",
            notes=["multiple alias candidates"],
        )

    alias = matches[0][1]
    confidence = (
        ResolutionConfidence.EXACT
        if alias.mapping_type.value == "canonical_alias"
        else ResolutionConfidence.CONTEXTUAL
    )
    concepts = ResolvedConcepts(
        primitive=primitive,
        event_type=alias.event_type_key,
        action=alias.action_key,
        state_dimension=alias.dimension_key,
        state_value=alias.value_key,
        relation_type=alias.canonical_key if primitive is PrimitiveKind.RELATION else None,
        attribute=alias.attribute_key,
        domains=list(alias.domain_keys),
        confidence=confidence,
        provenance=ResolutionProvenance.ALIAS,
        unresolved=False,
        resolution_status=ResolutionStatus.RESOLVED,
        recognized_sense=_primary_recognized_sense(senses),
        surface_expression=surface,
        notes=[f"alias={sorted(alias.expressions)}"],
    )
    if primitive is PrimitiveKind.RELATION:
        concepts = concepts.model_copy(update={"relation_type": alias.canonical_key})
    _publish_trained_alias(alias)
    return _validate_keys(concepts)
