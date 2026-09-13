"""Identity vs role: one named person, not Entity(role) --named--> Entity(name).

Does not read raw_input. Does not map Portuguese/English/Spanish copulas.
Identity-naming predicates are closed lemmas already interpreted by the LLM:
named / called / name / is_called / aka / identity.

Profession is a PROPERTY of the person. The role toward the principal is a
RELATION. Those are not the same claim (ADR 0093).
"""

from __future__ import annotations

from pke.interpretation.semantic.models import (
    SemanticClaim,
    SemanticClaimKind,
    SemanticClaimOrigin,
    SemanticEntityMention,
    SemanticProposal,
)
from pke.interpretation.semantic.owned_object import actor_mention
from pke.ontology.relation_metadata import RELATION_METADATA
from pke.resolution.self_ref import is_self_semantic_mention

IDENTITY_NAMING_LEMMAS = frozenset(
    {"named", "called", "name", "is_called", "aka", "identity"}
)
_PERSON_CLASS = frozenset({"person", "human", "people"})
_NON_PROFESSION_PREDICATES = frozenset(
    {
        *IDENTITY_NAMING_LEMMAS,
        "own",
        "owns",
        *(key.rsplit(".", 1)[-1] for key in RELATION_METADATA),
        *(
            meta.inverse.rsplit(".", 1)[-1]
            for meta in RELATION_METADATA.values()
            if meta.inverse
        ),
    }
)


def is_identity_naming_predicate(predicate: str | None) -> bool:
    text = (predicate or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return False
    if text.startswith("relation."):
        text = text.split(".", 1)[-1]
    return text in IDENTITY_NAMING_LEMMAS


def persistable_identity_keys(proposal: SemanticProposal) -> frozenset[str]:
    from pke.interpretation.semantic.owned_object import identity_mentions

    keys: set[str] = set()
    for mention in identity_mentions(proposal):
        if mention is None or not mention.text:
            continue
        if is_self_semantic_mention(mention):
            continue
        keys.add(mention.text.strip().casefold())
    return frozenset(keys)


def slot_identity_keys(proposal: SemanticProposal) -> frozenset[str]:
    keys: set[str] = set()
    for mention in (
        proposal.subject,
        proposal.object,
        proposal.context,
        *proposal.participants,
        *proposal.entities_mentioned,
    ):
        if mention is None or not mention.text:
            continue
        if is_self_semantic_mention(mention):
            continue
        if mention.reference_kind == "class":
            continue
        keys.add(mention.text.strip().casefold())
    return frozenset(keys)


def fold_identity_naming(proposal: SemanticProposal) -> SemanticProposal:
    """Collapse role-noun + identity-name into one persistable entity + role relation."""
    if proposal.correction_semantics:
        return proposal
    if proposal.utterance_kind == "query":
        return proposal
    possessed, named = _find_role_and_name(proposal)
    if possessed is not None and named is not None:
        if possessed.text.strip().casefold() != named.text.strip().casefold():
            if _is_personish(possessed) or _is_personish(named):
                proposal = _fold_person_role(proposal, possessed, named)
            elif _has_identity_naming_signal(proposal):
                proposal = _fold_owned_named_instance(proposal, possessed, named)
    return _ensure_profession_property(proposal)


def _find_role_and_name(
    proposal: SemanticProposal,
) -> tuple[SemanticEntityMention | None, SemanticEntityMention | None]:
    possessed = _possessive_mentions(proposal)
    named = _named_mentions(proposal)
    value_named = _named_from_identity_value(proposal)
    if value_named is not None and all(
        item.text.strip().casefold() != value_named.text.strip().casefold() for item in named
    ):
        named = [*named, value_named]
    if len(possessed) != 1:
        return None, None
    role = possessed[0]
    others = [
        item
        for item in named
        if item.text.strip().casefold() != role.text.strip().casefold()
    ]
    if len(others) != 1:
        return None, None
    if not _eligible_for_fold(proposal, role, others[0]):
        return None, None
    return role, others[0]


def _eligible_for_fold(
    proposal: SemanticProposal,
    possessed: SemanticEntityMention,
    named: SemanticEntityMention,
) -> bool:
    if _has_identity_naming_signal(proposal):
        return True
    return _is_personish(possessed) or _is_personish(named)


def _has_identity_naming_signal(proposal: SemanticProposal) -> bool:
    if is_identity_naming_predicate(proposal.relation_expression):
        return True
    expr = (proposal.attribute_expression or "").strip().lower().replace(" ", "_")
    if expr in IDENTITY_NAMING_LEMMAS:
        return True
    for claim in proposal.claims:
        if claim.origin is not SemanticClaimOrigin.EXPLICIT:
            continue
        if claim.kind is SemanticClaimKind.RELATION and is_identity_naming_predicate(
            claim.predicate
        ):
            return True
        if claim.kind is SemanticClaimKind.INTRINSIC_PROPERTY:
            dim = (claim.dimension or claim.predicate or "").strip().lower()
            if dim in {"name", "canonical_name"}:
                return True
        if claim.kind is SemanticClaimKind.ATTRIBUTE:
            dim = (claim.dimension or claim.predicate or "").strip().lower()
            if dim in IDENTITY_NAMING_LEMMAS:
                return True
    return False


def _fold_person_role(
    proposal: SemanticProposal,
    possessed: SemanticEntityMention,
    named: SemanticEntityMention,
) -> SemanticProposal:
    person = named.model_copy(
        update={
            "kind_hint": "person",
            "class_hint": named.class_hint or "person",
            "reference_kind": "named",
        }
    )
    role = _role_lemma(possessed)
    self_m = actor_mention()
    mapping = {possessed.text: person}
    claims: list[SemanticClaim] = [
        SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=person),
        SemanticClaim(
            kind=SemanticClaimKind.CLASSIFICATION,
            subject=person,
            class_hint="person",
        ),
        SemanticClaim(
            kind=SemanticClaimKind.INTRINSIC_PROPERTY,
            subject=person,
            dimension="name",
            value_text=person.text,
        ),
        SemanticClaim(
            kind=SemanticClaimKind.ATTRIBUTE,
            subject=person,
            dimension="profession",
            predicate="profession",
            value_text=role,
        ),
        SemanticClaim(
            kind=SemanticClaimKind.RELATION,
            predicate=role,
            subject=self_m,
            object=person,
        ),
    ]
    claims.extend(_rewritten_companion_claims(proposal, mapping, possessed.text, person.text))
    mentioned = [
        item
        for item in proposal.entities_mentioned
        if item.text.strip().casefold()
        not in {possessed.text.strip().casefold(), person.text.strip().casefold()}
    ]
    mentioned.append(person)
    return proposal.model_copy(
        update={
            "subject": self_m,
            "object": person,
            "context": None,
            "entities_mentioned": mentioned,
            "participants": [
                item
                for item in proposal.participants
                if item.text.strip().casefold() != possessed.text.strip().casefold()
            ],
            "relation_expression": role,
            "link_semantics": True,
            "classification_semantics": True,
            "primitive_hint": "relation",
            "attribute_expression": None,
            "claims": _dedupe_claims(claims),
        }
    )


def _fold_owned_named_instance(
    proposal: SemanticProposal,
    possessed: SemanticEntityMention,
    named: SemanticEntityMention,
) -> SemanticProposal:
    instance = named.model_copy(
        update={
            "kind_hint": named.kind_hint or possessed.kind_hint or "thing",
            "class_hint": named.class_hint or possessed.class_hint,
            "reference_kind": "named",
        }
    )
    self_m = actor_mention()
    mapping = {possessed.text: instance}
    class_hint = instance.class_hint
    claims: list[SemanticClaim] = [
        SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=instance),
        SemanticClaim(
            kind=SemanticClaimKind.RELATION,
            predicate="owns",
            subject=self_m,
            object=instance,
        ),
        SemanticClaim(
            kind=SemanticClaimKind.INTRINSIC_PROPERTY,
            subject=instance,
            dimension="name",
            value_text=instance.text,
        ),
    ]
    if class_hint:
        claims.append(
            SemanticClaim(
                kind=SemanticClaimKind.CLASSIFICATION,
                subject=instance,
                class_hint=class_hint,
            )
        )
    claims.extend(_rewritten_companion_claims(proposal, mapping, possessed.text, instance.text))
    mentioned = [
        item
        for item in proposal.entities_mentioned
        if item.text.strip().casefold()
        not in {possessed.text.strip().casefold(), instance.text.strip().casefold()}
    ]
    mentioned.append(instance)
    return proposal.model_copy(
        update={
            "subject": self_m,
            "object": instance,
            "entities_mentioned": mentioned,
            "relation_expression": "owns",
            "link_semantics": True,
            "classification_semantics": True,
            "primitive_hint": "relation",
            "claims": _dedupe_claims(claims),
        }
    )


def _rewritten_companion_claims(
    proposal: SemanticProposal,
    mapping: dict[str, SemanticEntityMention],
    possessed_text: str,
    identity_text: str,
) -> list[SemanticClaim]:
    kept: list[SemanticClaim] = []
    possessed_fold = possessed_text.strip().casefold()
    identity_fold = identity_text.strip().casefold()
    for claim in proposal.claims:
        if claim.origin is not SemanticClaimOrigin.EXPLICIT:
            continue
        if claim.kind is SemanticClaimKind.RELATION and is_identity_naming_predicate(
            claim.predicate
        ):
            continue
        if claim.kind is SemanticClaimKind.ENTITY:
            target = claim.subject or claim.object
            if target is not None and target.text.strip().casefold() == possessed_fold:
                continue
        if claim.kind is SemanticClaimKind.CLASSIFICATION:
            target = claim.subject or claim.object
            if target is not None and target.text.strip().casefold() == possessed_fold:
                continue
        if claim.kind is SemanticClaimKind.INTRINSIC_PROPERTY:
            dim = (claim.dimension or claim.predicate or "").strip().lower()
            if dim in {"name", "canonical_name"}:
                continue
        if claim.kind is SemanticClaimKind.RELATION:
            pred = (claim.predicate or "").strip().lower()
            if pred in {"owns", "own"} or pred.endswith(".owns"):
                continue
        rewritten = claim.model_copy(
            update={
                "subject": _map_mention(claim.subject, mapping),
                "object": _map_mention(claim.object, mapping),
            }
        )
        if rewritten.kind is SemanticClaimKind.RELATION:
            subj = rewritten.subject
            obj = rewritten.object
            if (
                subj is not None
                and obj is not None
                and subj.text.strip().casefold() == identity_fold
                and obj.text.strip().casefold() == identity_fold
            ):
                continue
        kept.append(rewritten)
    return kept


def _map_mention(
    mention: SemanticEntityMention | None,
    mapping: dict[str, SemanticEntityMention],
) -> SemanticEntityMention | None:
    if mention is None:
        return None
    return mapping.get(mention.text, mention)


def _dedupe_claims(claims: list[SemanticClaim]) -> list[SemanticClaim]:
    seen: set[tuple] = set()
    unique: list[SemanticClaim] = []
    for claim in claims:
        key = (
            claim.kind.value,
            claim.subject.text if claim.subject else None,
            claim.object.text if claim.object else None,
            claim.predicate,
            claim.class_hint,
            claim.dimension,
            claim.value_text,
            claim.numeric_value,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(claim)
    return unique


def _ensure_profession_property(proposal: SemanticProposal) -> SemanticProposal:
    """Profession is a property; the role relation to principal is separate."""
    person = None
    lemma = None
    for claim in proposal.claims:
        if claim.kind is not SemanticClaimKind.RELATION:
            continue
        cand = _profession_lemma_from_predicate(claim.predicate)
        if cand is None:
            continue
        subj, obj = claim.subject, claim.object
        if subj is None or obj is None:
            continue
        if is_self_semantic_mention(subj) and _is_personish(obj):
            person, lemma = obj, cand
            break
        if is_self_semantic_mention(obj) and _is_personish(subj):
            person, lemma = subj, cand
            break
    if person is None:
        lemma = _profession_lemma_from_predicate(proposal.relation_expression)
        obj = proposal.object
        subj = proposal.subject
        if lemma and obj is not None and subj is not None:
            if is_self_semantic_mention(subj) and _is_personish(obj):
                person = obj
            elif is_self_semantic_mention(obj) and _is_personish(subj):
                person = subj
    if person is None or lemma is None:
        return proposal
    if _has_profession_claim(proposal, person):
        return proposal
    extra = SemanticClaim(
        kind=SemanticClaimKind.ATTRIBUTE,
        subject=person,
        dimension="profession",
        predicate="profession",
        value_text=lemma,
    )
    return proposal.model_copy(update={"claims": _dedupe_claims([*proposal.claims, extra])})


def _has_profession_claim(
    proposal: SemanticProposal, person: SemanticEntityMention
) -> bool:
    fold = person.text.strip().casefold()
    for claim in proposal.claims:
        if claim.kind is not SemanticClaimKind.ATTRIBUTE:
            continue
        dim = (claim.dimension or claim.predicate or "").strip().lower()
        if dim != "profession":
            continue
        if claim.subject is not None and claim.subject.text.strip().casefold() == fold:
            return True
    return False


def _profession_lemma_from_predicate(predicate: str | None) -> str | None:
    text = (predicate or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return None
    if text.startswith("relation.learned."):
        text = text.split(".", 2)[-1]
    elif text.startswith("relation."):
        text = text.split(".", 1)[-1]
    if text.endswith("_of"):
        text = text[:-3]
    if text.startswith("has_"):
        text = text[4:]
    if not text or text in _NON_PROFESSION_PREDICATES or text in _PERSON_CLASS:
        return None
    if text == "role":
        return None
    return text


def _role_lemma(possessed: SemanticEntityMention) -> str:
    for token in (possessed.class_hint, possessed.role_hint, possessed.text):
        text = (token or "").strip()
        if not text:
            continue
        if text.replace("-", "_").replace(" ", "_").lower() in _PERSON_CLASS:
            continue
        return text.replace(" ", "_")
    return "role"


def _is_personish(mention: SemanticEntityMention) -> bool:
    if mention.kind_hint == "person":
        return True
    hint = (mention.class_hint or "").strip().lower()
    return hint in _PERSON_CLASS


def _possessive_mentions(proposal: SemanticProposal) -> list[SemanticEntityMention]:
    found: list[SemanticEntityMention] = []
    seen: set[str] = set()

    def add(mention: SemanticEntityMention | None) -> None:
        if mention is None or not mention.text:
            return
        if mention.reference_kind != "possessive":
            return
        if is_self_semantic_mention(mention):
            return
        key = mention.text.strip().casefold()
        if key in seen:
            return
        seen.add(key)
        found.append(mention)

    add(proposal.subject)
    add(proposal.object)
    add(proposal.context)
    for mention in (*proposal.participants, *proposal.entities_mentioned):
        add(mention)
    for claim in proposal.claims:
        if claim.origin is SemanticClaimOrigin.EXPLICIT:
            add(claim.subject)
            add(claim.object)
    return found


def _named_mentions(proposal: SemanticProposal) -> list[SemanticEntityMention]:
    found: list[SemanticEntityMention] = []
    seen: set[str] = set()

    def add(mention: SemanticEntityMention | None) -> None:
        if mention is None or not mention.text:
            return
        if mention.reference_kind != "named":
            return
        if is_self_semantic_mention(mention):
            return
        key = mention.text.strip().casefold()
        if key in seen:
            return
        seen.add(key)
        found.append(mention)

    add(proposal.subject)
    add(proposal.object)
    add(proposal.context)
    for mention in (*proposal.participants, *proposal.entities_mentioned):
        add(mention)
    for claim in proposal.claims:
        if claim.origin is SemanticClaimOrigin.EXPLICIT:
            add(claim.subject)
            add(claim.object)
    return found


def _named_from_identity_value(proposal: SemanticProposal) -> SemanticEntityMention | None:
    for claim in proposal.claims:
        if claim.origin is not SemanticClaimOrigin.EXPLICIT:
            continue
        dim = (claim.dimension or claim.predicate or "").strip().lower()
        if claim.kind is SemanticClaimKind.INTRINSIC_PROPERTY and dim in {
            "name",
            "canonical_name",
        }:
            value = (claim.value_text or claim.value_key or "").strip()
            if not value:
                continue
            subject = claim.subject
            kind = subject.kind_hint if subject is not None else "person"
            return SemanticEntityMention(
                text=value,
                kind_hint=kind,
                class_hint="person" if kind == "person" else (subject.class_hint if subject else None),
                reference_kind="named",
                confidence=1.0,
            )
        if claim.kind is SemanticClaimKind.ATTRIBUTE and dim in IDENTITY_NAMING_LEMMAS:
            value = (claim.value_text or claim.value_key or "").strip()
            if not value:
                continue
            subject = claim.subject
            kind = subject.kind_hint if subject is not None else None
            return SemanticEntityMention(
                text=value,
                kind_hint=kind,
                class_hint=subject.class_hint if subject is not None else None,
                reference_kind="named",
                confidence=1.0,
            )
    return None
