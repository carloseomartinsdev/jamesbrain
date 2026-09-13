"""Read-only projection of UserKnowledgeSnapshot for the Knowledge Inspector.

Walks persisted relations. Does not infer ontology edges, rewrite types, or mutate.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict, deque
from datetime import datetime
from decimal import Decimal

from pke.domain.attributes import EntityAttribute
from pke.domain.entities import Entity
from pke.domain.events import Event
from pke.domain.measurements import Measurement
from pke.domain.relations import Relation
from pke.domain.states import State
from pke.ontology.registry import OntologyRegistry
from pke.persist.snapshot import UserKnowledgeSnapshot
from pke.persist.sqlite.read_store import SqliteKnowledgeReadStore
from pke.product.knowledge.dtos import (
    DEFAULT_DEPTH,
    MAX_DEPTH,
    MAX_GRAPH_EDGES,
    MAX_GRAPH_NODES,
    MAX_SEARCH_RESULTS,
    KnowledgeAttribute,
    KnowledgeEdge,
    KnowledgeEntityResponse,
    KnowledgeEvent,
    KnowledgeGraphMeta,
    KnowledgeGraphResponse,
    KnowledgeIntrinsic,
    KnowledgeMeasurement,
    KnowledgeNode,
    KnowledgeRelationRef,
    KnowledgeSearchHit,
    KnowledgeSearchResponse,
    KnowledgeState,
    KnowledgeTypeInfo,
)

_LOG = logging.getLogger("pke.product")

_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class KnowledgeNotFound(Exception):
    pass


class KnowledgeInvalidId(Exception):
    pass


class KnowledgeInspector:
    def __init__(self, store: SqliteKnowledgeReadStore, ontology: OntologyRegistry) -> None:
        self._store = store
        self._ontology = ontology

    def graph(
        self,
        user_id: str,
        *,
        root_entity_id: str | None = None,
        depth: int = DEFAULT_DEPTH,
        current_only: bool = True,
        expand_entity_id: str | None = None,
    ) -> KnowledgeGraphResponse:
        root_entity_id = self._optional_id(root_entity_id)
        expand_entity_id = self._optional_id(expand_entity_id)
        depth = self._clamp_depth(depth)
        snapshot = self._store.load_user_graph(user_id)
        if root_entity_id is not None and root_entity_id not in snapshot.entities:
            raise KnowledgeNotFound()
        if expand_entity_id is not None and expand_entity_id not in snapshot.entities:
            raise KnowledgeNotFound()

        root = root_entity_id or snapshot.principal_entity_id
        seeds: list[tuple[str, int]] = []
        if root is not None and root in snapshot.entities:
            seeds.append((root, depth))
        if expand_entity_id is not None:
            seeds.append((expand_entity_id, 1))

        nodes, edges, truncated = self._walk(snapshot, seeds, current_only=current_only)
        return KnowledgeGraphResponse(
            nodes=nodes,
            edges=edges,
            truncated=truncated,
            meta=KnowledgeGraphMeta(
                root_entity_id=root if root in snapshot.entities else None,
                principal_entity_id=snapshot.principal_entity_id,
                depth=depth,
                current_only=current_only,
                expand_entity_id=expand_entity_id,
                node_count=len(nodes),
                edge_count=len(edges),
            ),
        )

    def entity(
        self,
        user_id: str,
        entity_id: str,
        *,
        current_only: bool = True,
    ) -> KnowledgeEntityResponse:
        entity_id = self._require_id(entity_id)
        snapshot = self._store.load_user_graph(user_id)
        entity = snapshot.entities.get(entity_id)
        if entity is None:
            raise KnowledgeNotFound()
        detail = self._entity_detail(snapshot, entity, current_only=current_only)
        _LOG.info(
            "knowledge_inspector_entity entity_id=%s attributes=%s measurements=%s relations=%s states=%s events=%s",
            detail.entity_id,
            len(detail.attributes),
            len(detail.measurements),
            len(detail.relations_incoming) + len(detail.relations_outgoing),
            len(detail.states),
            len(detail.events),
        )
        return detail

    def search(
        self,
        user_id: str,
        q: str,
        *,
        type_key: str | None = None,
        limit: int = MAX_SEARCH_RESULTS,
    ) -> KnowledgeSearchResponse:
        needle = (q or "").strip().lower()
        if len(needle) > 200:
            needle = needle[:200]
        type_filter = (type_key or "").strip().lower() or None
        cap = min(max(int(limit), 1), MAX_SEARCH_RESULTS)
        snapshot = self._store.load_user_graph(user_id)
        hits: list[tuple[int, KnowledgeSearchHit]] = []
        for entity in snapshot.entities.values():
            info = self._type_info(entity.type_id)
            if type_filter and type_filter not in {
                info.key.lower(),
                info.id.lower(),
                (info.source or "").lower(),
            }:
                continue
            rank = self._search_rank(entity, info, needle) if needle else 50
            if rank is None:
                continue
            hits.append(
                (
                    rank,
                    KnowledgeSearchHit(
                        id=entity.id,
                        canonical_name=entity.canonical_name,
                        label=self._entity_label(snapshot, entity),
                        type=info.key,
                        type_id=info.id,
                        role="principal" if entity.id == snapshot.principal_entity_id else None,
                    ),
                )
            )
        hits.sort(key=lambda item: (item[0], item[1].canonical_name.lower(), item[1].id))
        truncated = len(hits) > cap
        return KnowledgeSearchResponse(
            items=[item[1] for item in hits[:cap]],
            truncated=truncated,
            limit=cap,
        )

    def _walk(
        self,
        snapshot: UserKnowledgeSnapshot,
        seeds: list[tuple[str, int]],
        *,
        current_only: bool,
    ) -> tuple[list[KnowledgeNode], list[KnowledgeEdge], bool]:
        adj: dict[str, list[Relation]] = defaultdict(list)
        for rel in snapshot.relations:
            if current_only and not rel.is_current:
                continue
            adj[rel.from_id].append(rel)
            if rel.to_id != rel.from_id:
                adj[rel.to_id].append(rel)

        remaining: dict[str, int] = {}
        queue: deque[str] = deque()
        for seed, depth in seeds:
            if seed not in snapshot.entities:
                continue
            if depth > remaining.get(seed, -1):
                remaining[seed] = depth
                queue.append(seed)

        entity_ids: list[str] = []
        seen_entity: set[str] = set()
        edge_ids: set[str] = set()
        edges: list[KnowledgeEdge] = []
        truncated = False

        def admit_entity(eid: str) -> bool:
            nonlocal truncated
            if eid in seen_entity:
                return True
            projected = len(seen_entity) + 1 + self._type_budget(snapshot, eid, seen_entity)
            if projected > MAX_GRAPH_NODES:
                truncated = True
                return False
            seen_entity.add(eid)
            entity_ids.append(eid)
            return True

        for seed in list(remaining):
            if not admit_entity(seed):
                break

        while queue:
            eid = queue.popleft()
            hops_left = remaining.get(eid, 0)
            if hops_left <= 0:
                continue
            for rel in adj.get(eid, []):
                if rel.id not in edge_ids:
                    if len(edges) >= MAX_GRAPH_EDGES:
                        truncated = True
                        break
                    edge_ids.add(rel.id)
                    edges.append(self._relation_edge(rel))
                neighbor = rel.to_id if rel.from_id == eid else rel.from_id
                if neighbor not in snapshot.entities:
                    continue
                nxt = hops_left - 1
                if neighbor not in seen_entity:
                    if not admit_entity(neighbor):
                        continue
                if nxt > remaining.get(neighbor, -1):
                    remaining[neighbor] = nxt
                    queue.append(neighbor)
            if truncated:
                break

        nodes: list[KnowledgeNode] = []
        node_ids: set[str] = set()
        for eid in entity_ids:
            entity = snapshot.entities[eid]
            node = self._entity_node(snapshot, entity)
            nodes.append(node)
            node_ids.add(node.id)
            type_node = self._type_node(entity.type_id)
            if type_node.id not in node_ids:
                if len(nodes) >= MAX_GRAPH_NODES:
                    truncated = True
                    break
                nodes.append(type_node)
                node_ids.add(type_node.id)
            class_edge = self._classification_edge(entity)
            if class_edge.id not in edge_ids:
                if len(edges) >= MAX_GRAPH_EDGES:
                    truncated = True
                    break
                if class_edge.target in node_ids:
                    edge_ids.add(class_edge.id)
                    edges.append(class_edge)

        return nodes, edges, truncated

    def _type_budget(self, snapshot: UserKnowledgeSnapshot, eid: str, seen: set[str]) -> int:
        entity = snapshot.entities.get(eid)
        if entity is None:
            return 0
        type_id = entity.type_id
        if type_id in seen:
            return 0
        for other in seen:
            other_ent = snapshot.entities.get(other)
            if other_ent is not None and other_ent.type_id == type_id:
                return 0
        return 1

    def _entity_detail(
        self,
        snapshot: UserKnowledgeSnapshot,
        entity: Entity,
        *,
        current_only: bool,
    ) -> KnowledgeEntityResponse:
        type_info = self._type_info(entity.type_id)
        role = "principal" if entity.id == snapshot.principal_entity_id else None
        outgoing: list[KnowledgeRelationRef] = []
        incoming: list[KnowledgeRelationRef] = []
        for rel in snapshot.relations:
            if current_only and not rel.is_current:
                continue
            if rel.from_id == entity.id:
                outgoing.append(self._relation_ref(snapshot, rel))
            if rel.to_id == entity.id:
                incoming.append(self._relation_ref(snapshot, rel))
        attributes = [
            self._attribute_dto(attr)
            for attr in snapshot.attributes
            if attr.entity_id == entity.id and (attr.is_current or not current_only)
        ]
        measurements = [
            self._measurement_dto(item)
            for item in snapshot.measurements
            if item.entity_id == entity.id
        ]
        measurements.sort(key=lambda item: (item.dimension_key, item.created_at or "", item.id))
        states = [
            self._state_dto(state)
            for state in snapshot.states
            if state.entity_id == entity.id and (state.is_current or not current_only)
        ]
        events = [
            self._event_dto(event)
            for event in snapshot.events
            if self._event_touches(event, entity.id)
        ]
        intrinsic = [
            KnowledgeIntrinsic(key="canonical_name", value=entity.canonical_name),
            KnowledgeIntrinsic(key="type", value=type_info.key),
            KnowledgeIntrinsic(key="type_id", value=type_info.id),
            KnowledgeIntrinsic(key="aliases", value=list(entity.aliases)),
            KnowledgeIntrinsic(key="created_at", value=self._dt(entity.created_at)),
        ]
        if role:
            intrinsic.append(KnowledgeIntrinsic(key="role", value=role))
        raw = {
            "entity": entity.model_dump(mode="json"),
            "type": type_info.model_dump(mode="json"),
            "relations_outgoing": [item.model_dump(mode="json") for item in outgoing],
            "relations_incoming": [item.model_dump(mode="json") for item in incoming],
            "attributes": [item.model_dump(mode="json") for item in attributes],
            "measurements": [item.model_dump(mode="json") for item in measurements],
            "states": [item.model_dump(mode="json") for item in states],
            "events": [item.model_dump(mode="json") for item in events],
        }
        return KnowledgeEntityResponse(
            entity_id=entity.id,
            canonical_name=entity.canonical_name,
            aliases=list(entity.aliases),
            role=role,
            type=type_info,
            status="current",
            created_at=self._dt(entity.created_at),
            intrinsic=intrinsic,
            relations_outgoing=outgoing,
            relations_incoming=incoming,
            attributes=attributes,
            measurements=measurements,
            states=states,
            events=events,
            raw=raw,
        )

    def _entity_node(self, snapshot: UserKnowledgeSnapshot, entity: Entity) -> KnowledgeNode:
        info = self._type_info(entity.type_id)
        role = "principal" if entity.id == snapshot.principal_entity_id else None
        return KnowledgeNode(
            id=entity.id,
            kind="entity",
            label=self._entity_label(snapshot, entity),
            type=info.key,
            type_id=info.id,
            canonical_name=entity.canonical_name,
            visual=self._entity_visual(info.key, role is not None),
            role=role,
            aliases=list(entity.aliases),
            scope=info.scope,
            ontology_kind=info.ontology_kind,
        )

    def _type_node(self, type_id: str) -> KnowledgeNode:
        info = self._type_info(type_id)
        return KnowledgeNode(
            id=info.id,
            kind="type",
            label=info.key,
            type=info.key,
            type_id=info.id,
            canonical_name=info.key,
            visual="concept",
            scope=info.scope,
            ontology_kind=info.ontology_kind,
        )

    def _classification_edge(self, entity: Entity) -> KnowledgeEdge:
        info = self._type_info(entity.type_id)
        return KnowledgeEdge(
            id=f"class:{entity.id}",
            source=entity.id,
            target=info.id,
            type="type",
            label="type",
            kind="classification",
            is_current=True,
        )

    def _relation_edge(self, rel: Relation) -> KnowledgeEdge:
        return KnowledgeEdge(
            id=rel.id,
            source=rel.from_id,
            target=rel.to_id,
            type=rel.key,
            label=self._short_relation_label(rel.key),
            kind="relation",
            is_current=rel.is_current,
            valid_from=self._dt(rel.valid_from),
            valid_to=self._dt(rel.valid_to),
            confidence=rel.confidence.score if rel.confidence else None,
            raw_input_id=rel.raw_input_id,
            source_kind=rel.source.kind.value if rel.source else None,
            source_id=rel.source.id if rel.source else None,
            created_at=self._dt(rel.created_at),
            observed_at=self._dt(rel.observed_at),
        )

    def _relation_ref(self, snapshot: UserKnowledgeSnapshot, rel: Relation) -> KnowledgeRelationRef:
        src = snapshot.entities.get(rel.from_id)
        dst = snapshot.entities.get(rel.to_id)
        return KnowledgeRelationRef(
            id=rel.id,
            type=rel.key,
            label=self._short_relation_label(rel.key),
            from_id=rel.from_id,
            to_id=rel.to_id,
            from_label=self._entity_label(snapshot, src) if src else rel.from_id,
            to_label=self._entity_label(snapshot, dst) if dst else rel.to_id,
            is_current=rel.is_current,
            valid_from=self._dt(rel.valid_from),
            valid_to=self._dt(rel.valid_to),
            confidence=rel.confidence.score if rel.confidence else None,
            raw_input_id=rel.raw_input_id,
            source_kind=rel.source.kind.value if rel.source else None,
            source_id=rel.source.id if rel.source else None,
            created_at=self._dt(rel.created_at),
            observed_at=self._dt(rel.observed_at),
        )

    def _measurement_dto(self, item: Measurement) -> KnowledgeMeasurement:
        number = format(Decimal(item.numeric_value), "f")
        if item.currency_code:
            display = f"{number} {item.currency_code}"
        elif item.unit:
            display = f"{number} {item.unit}"
        else:
            display = number
        return KnowledgeMeasurement(
            id=item.id,
            dimension_key=item.dimension_key,
            dimension_concept_id=item.dimension_concept_id,
            numeric_value=number,
            unit=item.unit,
            currency_code=item.currency_code,
            display_value=display,
            context_entity_id=item.context_entity_id,
            confidence=item.confidence.score if item.confidence else None,
            raw_input_id=item.raw_input_id,
            source_kind=item.source.kind.value if item.source else None,
            source_id=item.source.id if item.source else None,
            created_at=self._dt(item.created_at),
            observed_at=self._dt(item.observed_at),
        )

    def _event_touches(self, event: Event, entity_id: str) -> bool:
        if event.actor_id == entity_id or event.subject_id == entity_id:
            return True
        return entity_id in event.participant_entity_ids()

    def _event_dto(self, event: Event) -> KnowledgeEvent:
        info = self._type_info(event.type_id)
        return KnowledgeEvent(
            id=event.id,
            type=info.key,
            type_id=event.type_id,
            action_id=event.action_id,
            status=event.status.value,
            actor_id=event.actor_id,
            subject_id=event.subject_id,
            raw_input_id=event.raw_input_id,
            created_at=self._dt(event.created_at),
        )

    def _attribute_dto(self, attr: EntityAttribute) -> KnowledgeAttribute:
        label, source = self._attribute_dimension_meta(attr.dimension_key)
        return KnowledgeAttribute(
            id=attr.id,
            dimension_key=attr.dimension_key,
            dimension_concept_id=attr.dimension_concept_id,
            dimension_label=label,
            dimension_source=source,
            value=self._attribute_value(attr),
            value_kind=attr.value_kind.value,
            unit=attr.unit,
            is_current=attr.is_current,
            valid_from=self._dt(attr.valid_from),
            valid_to=self._dt(attr.valid_to),
            confidence=attr.confidence.score if attr.confidence else None,
            raw_input_id=attr.raw_input_id,
            source_kind=attr.source.kind.value if attr.source else None,
            created_at=self._dt(attr.created_at),
            observed_at=self._dt(attr.observed_at),
        )

    def _state_dto(self, state: State) -> KnowledgeState:
        return KnowledgeState(
            id=state.id,
            dimension_key=state.dimension_key,
            value_key=state.value_key,
            is_current=state.is_current,
            valid_from=self._dt(state.valid_from),
            valid_to=self._dt(state.valid_to),
            raw_input_id=state.raw_input_id,
            created_at=self._dt(state.created_at),
        )

    def _type_info(self, type_id: str) -> KnowledgeTypeInfo:
        concept = self._ontology.get_by_id(type_id)
        if concept is None:
            key = type_id
            if type_id.startswith("core:"):
                key = type_id[5:]
            elif type_id.startswith("ext:"):
                key = type_id[4:]
            source = None
            if key.startswith("entity.learned.") or key.startswith("relation.learned.") or key.startswith("attribute.learned."):
                source = "learned"
            elif type_id.startswith("core:"):
                source = "core"
            elif type_id.startswith("ext:"):
                source = "extended"
            return KnowledgeTypeInfo(id=type_id, key=key, source=source)
        source = concept.scope.value
        if concept.key.startswith("entity.learned.") or concept.key.startswith("relation.learned.") or concept.key.startswith("attribute.learned."):
            source = "learned"
        return KnowledgeTypeInfo(
            id=concept.id,
            key=concept.key,
            scope=concept.scope.value,
            ontology_kind=concept.kind.value,
            source=source,
        )

    def _entity_label(self, snapshot: UserKnowledgeSnapshot, entity: Entity) -> str:
        name = (entity.canonical_name or "").strip()
        if name:
            return name
        for alias in entity.aliases:
            text = (alias or "").strip()
            if text:
                return text
        return entity.id

    def _entity_visual(self, type_key: str, is_principal: bool) -> str:
        if is_principal or type_key == "entity.person":
            return "person"
        if type_key.startswith("entity.learned."):
            return "learned"
        if type_key.startswith("entity."):
            return "core"
        return "entity"

    def _short_relation_label(self, key: str) -> str:
        if key.startswith("relation.learned."):
            return key[len("relation.learned.") :]
        if key.startswith("relation."):
            return key[len("relation.") :]
        return key

    def _attribute_value(self, attr: EntityAttribute) -> str:
        if attr.text_value is not None:
            return attr.text_value
        if attr.numeric_value is not None:
            number = format(Decimal(attr.numeric_value), "f")
            return f"{number} {attr.unit}".strip() if attr.unit else number
        if attr.year_value is not None:
            return str(attr.year_value)
        if attr.date_value is not None:
            return attr.date_value.isoformat()
        if attr.concept_value_id is not None:
            return self._type_info(attr.concept_value_id).key
        return ""

    def _attribute_dimension_meta(self, key: str) -> tuple[str | None, str | None]:
        source = None
        if key.startswith("attribute.learned."):
            source = "learned"
        concept = self._ontology.get_by_key(key)
        if concept is not None and concept.presentation is not None and concept.presentation.label:
            return concept.presentation.label, source or (
                "learned" if key.startswith("attribute.learned.") else concept.scope.value
            )
        if key.startswith("attribute.learned."):
            return key[len("attribute.learned.") :].replace("_", " "), "learned"
        return key, source

    def _search_rank(self, entity: Entity, info: KnowledgeTypeInfo, needle: str) -> int | None:
        cid = entity.id.lower()
        name = entity.canonical_name.lower()
        aliases = [a.lower() for a in entity.aliases]
        type_key = info.key.lower()
        if needle == cid or needle == name:
            return 0
        if any(needle == a for a in aliases):
            return 1
        if name.startswith(needle):
            return 2
        if needle in name:
            return 3
        if any(needle in a for a in aliases):
            return 4
        if needle in cid:
            return 5
        if needle in type_key or needle in info.id.lower():
            return 6
        return None

    def _optional_id(self, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if text == "":
            return None
        return self._require_id(text)

    def _require_id(self, value: str) -> str:
        text = value.strip()
        if not _ID_RE.fullmatch(text):
            raise KnowledgeInvalidId()
        return text

    def _clamp_depth(self, depth: int) -> int:
        try:
            value = int(depth)
        except (TypeError, ValueError):
            return DEFAULT_DEPTH
        return max(1, min(MAX_DEPTH, value))

    def _dt(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()
