"""Principal Binding — Auth principal → world-model Entity (E1.1).

AuthUser.id remains distinct from Entity.id.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict

from pke.domain.entities import Entity
from pke.domain.ids import new_ulid
from pke.ontology.seeds import core_concept_id

# Neutral bootstrap label — not a spoken personal name (D-E1-04).
PRINCIPAL_CANONICAL_NAME = "__principal__"
PRINCIPAL_ENTITY_TYPE_KEY = "entity.person"


class PrincipalBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    entity_id: str
    created_at: dt.datetime
    updated_at: dt.datetime
