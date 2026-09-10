"""Modelos ORM. Não são objetos de domínio."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class DecimalAsText(TypeDecorator):
    """Decimal canônico em texto. SQLite não tem NUMERIC real; evita float."""

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: object) -> str | None:
        if value is None:
            return None
        return format(Decimal(value), "f")

    def process_result_value(self, value: str | None, dialect: object) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value)


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SchemaMetaRow(Base):
    __tablename__ = "schema_meta"

    id: Mapped[int] = mapped_column(primary_key=True)
    storage_schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    core_schema_version: Mapped[str] = mapped_column(String(16), nullable=False)


class RawInputRow(Base):
    __tablename__ = "raw_inputs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EntityRow(Base):
    __tablename__ = "entities"
    __table_args__ = (Index("ix_entities_user_norm_name", "user_id", "normalized_canonical_name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    type_id: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_canonical_name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    aliases: Mapped[list[AliasRow]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )


class AliasRow(Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (Index("ix_aliases_user_norm", "user_id", "normalized_alias"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(256), nullable=False)
    entity: Mapped[EntityRow] = relationship(back_populates="aliases")


class SourceRow(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_input_id: Mapped[str | None] = mapped_column(ForeignKey("raw_inputs.id"), nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class EventRow(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_user_date", "user_id", "time_date"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    type_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"), nullable=True)
    subject_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_input_id: Mapped[str] = mapped_column(ForeignKey("raw_inputs.id"), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_original_text: Mapped[str] = mapped_column(Text, nullable=False)
    time_interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_instant: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    time_of_day: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    time_period_start: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    time_period_end: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    time_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    time_precision: Mapped[str] = mapped_column(String(32), nullable=False)
    time_day_period: Mapped[str | None] = mapped_column(String(16), nullable=True)
    time_resolution_rule: Mapped[str | None] = mapped_column(String(64), nullable=True)
    time_reference_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    time_reference_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    time_confidence_score: Mapped[float | None] = mapped_column(nullable=True)
    time_confidence_qualifier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="exact")
    temporal_relation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_occurrence_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_unknown_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_interval_start: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    temporal_interval_end: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    temporal_granularity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_tense_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    temporal_source_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rec_freq: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rec_interval: Mapped[int | None] = mapped_column(nullable=True)
    rec_by_monthday: Mapped[int | None] = mapped_column(nullable=True)
    rec_by_weekday: Mapped[int | None] = mapped_column(nullable=True)
    rec_until: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    rec_count: Mapped[int | None] = mapped_column(nullable=True)
    rec_rrule: Mapped[str | None] = mapped_column(Text, nullable=True)
    domains: Mapped[list[EventDomainRow]] = relationship(cascade="all, delete-orphan")
    participants: Mapped[list[EventParticipantRow]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )


class EventParticipantRow(Base):
    __tablename__ = "event_participants"
    __table_args__ = (
        UniqueConstraint("event_id", "entity_id", "role", name="uq_event_participant_role"),
        Index("ix_event_participants_event", "event_id"),
        Index("ix_event_participants_entity", "entity_id"),
        Index("ix_event_participants_event_role", "event_id", "role"),
        Index("ix_event_participants_entity_role", "entity_id", "role"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    event: Mapped[EventRow] = relationship(back_populates="participants")


class EventDomainRow(Base):
    __tablename__ = "event_domains"
    __table_args__ = (UniqueConstraint("event_id", "concept_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False)
    concept_id: Mapped[str] = mapped_column(String(128), nullable=False)


class FactRow(Base):
    __tablename__ = "facts"
    __table_args__ = (
        Index("ix_facts_user_concept", "user_id", "concept_id"),
        Index("ix_facts_about", "user_id", "about_kind", "about_id", "concept_id"),
        UniqueConstraint("supersedes_id", name="uq_facts_one_successor"),
        CheckConstraint("id != supersedes_id", name="ck_fact_no_self_supersede"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    about_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    about_id: Mapped[str] = mapped_column(String(32), nullable=False)
    concept_id: Mapped[str] = mapped_column(String(128), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_int: Mapped[int | None] = mapped_column(nullable=True)
    value_decimal: Mapped[Decimal | None] = mapped_column(DecimalAsText, nullable=True)
    value_bool: Mapped[bool | None] = mapped_column(nullable=True)
    money_amount: Mapped[Decimal | None] = mapped_column(DecimalAsText, nullable=True)
    money_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualifier: Mapped[str] = mapped_column(String(32), nullable=False)
    epistemic_status: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_score: Mapped[float] = mapped_column(nullable=False)
    confidence_qualifier: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("facts.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RelationRow(Base):
    __tablename__ = "relations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    from_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), nullable=False)
    to_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), nullable=False)
    type_id: Mapped[str] = mapped_column(String(128), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    is_current: Mapped[bool] = mapped_column(nullable=False, server_default="1")
    valid_from: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_original_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    time_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    time_instant: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_precision: Mapped[str] = mapped_column(String(32), nullable=False, server_default="partial")
    temporal_kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="partial")
    temporal_relation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_occurrence_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_unknown_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_interval_start: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    temporal_interval_end: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    temporal_granularity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_tense_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    temporal_source_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    caused_by_event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("relations.id"), nullable=True)
    raw_input_id: Mapped[str | None] = mapped_column(ForeignKey("raw_inputs.id"), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(nullable=True)
    confidence_qualifier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    term_time_original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    term_time_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    term_time_instant: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    term_time_precision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    term_temporal_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    term_temporal_relation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    term_temporal_occurrence_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    term_temporal_unknown_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    term_temporal_interval_start: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    term_temporal_interval_end: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    term_temporal_granularity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    term_temporal_tense_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    term_temporal_source_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    termination_observed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    termination_raw_input_id: Mapped[str | None] = mapped_column(ForeignKey("raw_inputs.id"), nullable=True)
    termination_source_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    termination_confidence_score: Mapped[float | None] = mapped_column(nullable=True)
    termination_confidence_qualifier: Mapped[str | None] = mapped_column(String(32), nullable=True)


class StateRow(Base):
    __tablename__ = "states"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), nullable=False)
    dimension_concept_id: Mapped[str] = mapped_column(String(128), nullable=False)
    dimension_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_concept_id: Mapped[str] = mapped_column(String(128), nullable=False)
    value_key: Mapped[str] = mapped_column(String(128), nullable=False)
    is_current: Mapped[bool] = mapped_column(nullable=False, server_default="1")
    payload_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_int: Mapped[int | None] = mapped_column(nullable=True)
    value_decimal: Mapped[Decimal | None] = mapped_column(DecimalAsText, nullable=True)
    value_bool: Mapped[bool | None] = mapped_column(nullable=True)
    money_amount: Mapped[Decimal | None] = mapped_column(DecimalAsText, nullable=True)
    money_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_original_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    time_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    time_instant: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_precision: Mapped[str] = mapped_column(String(32), nullable=False, server_default="partial")
    temporal_kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="partial")
    temporal_relation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_occurrence_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_unknown_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_interval_start: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    temporal_interval_end: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    temporal_granularity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_tense_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    temporal_source_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_from: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    caused_by_event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("states.id"), nullable=True)
    raw_input_id: Mapped[str | None] = mapped_column(ForeignKey("raw_inputs.id"), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(nullable=True)
    confidence_qualifier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EntityAttributeRow(Base):
    """Canonical Attribute primitive storage (schema v8)."""

    __tablename__ = "entity_attributes"
    __table_args__ = (
        Index("ix_entity_attributes_user", "user_id"),
        Index("ix_entity_attributes_entity", "entity_id"),
        Index("ix_entity_attributes_entity_dim", "entity_id", "dimension_key"),
        Index(
            "ix_entity_attributes_entity_dim_current",
            "entity_id",
            "dimension_key",
            "is_current",
        ),
        Index("ix_entity_attributes_dimension", "dimension_key"),
        CheckConstraint(
            "("
            "(value_kind = 'text' AND text_value IS NOT NULL AND numeric_value IS NULL "
            "AND year_value IS NULL AND date_value IS NULL AND concept_value_id IS NULL AND unit IS NULL) OR "
            "(value_kind = 'number' AND numeric_value IS NOT NULL AND text_value IS NULL "
            "AND year_value IS NULL AND date_value IS NULL AND concept_value_id IS NULL) OR "
            "(value_kind = 'year' AND year_value IS NOT NULL AND text_value IS NULL "
            "AND numeric_value IS NULL AND date_value IS NULL AND concept_value_id IS NULL AND unit IS NULL) OR "
            "(value_kind = 'date' AND date_value IS NOT NULL AND text_value IS NULL "
            "AND numeric_value IS NULL AND year_value IS NULL AND concept_value_id IS NULL AND unit IS NULL) OR "
            "(value_kind = 'concept' AND concept_value_id IS NOT NULL AND text_value IS NULL "
            "AND numeric_value IS NULL AND year_value IS NULL AND date_value IS NULL AND unit IS NULL)"
            ")",
            name="ck_entity_attributes_value_kind",
        ),
        CheckConstraint("id != supersedes_id", name="ck_entity_attribute_no_self_supersede"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), nullable=False)
    dimension_key: Mapped[str] = mapped_column(String(128), nullable=False)
    dimension_concept_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    value_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    concept_value_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    text_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    numeric_value: Mapped[Decimal | None] = mapped_column(DecimalAsText, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    date_value: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    year_value: Mapped[int | None] = mapped_column(nullable=True)
    time_original_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    time_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    time_instant: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_precision: Mapped[str] = mapped_column(String(32), nullable=False, server_default="partial")
    temporal_kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="unknown")
    temporal_relation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_occurrence_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_unknown_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_interval_start: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    temporal_interval_end: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    temporal_granularity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_tense_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    temporal_source_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_from: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(nullable=False, server_default="1")
    supersedes_id: Mapped[str | None] = mapped_column(
        ForeignKey("entity_attributes.id"), nullable=True
    )
    raw_input_id: Mapped[str | None] = mapped_column(ForeignKey("raw_inputs.id"), nullable=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(nullable=True)
    confidence_qualifier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MeasurementRow(Base):
    """Canonical Measurement primitive storage (schema v9). No is_current / supersedes_id."""

    __tablename__ = "measurements"
    __table_args__ = (
        Index("ix_measurements_user", "user_id"),
        Index("ix_measurements_entity", "entity_id"),
        Index("ix_measurements_entity_dim", "entity_id", "dimension_key"),
        Index(
            "ix_measurements_entity_dim_observed",
            "entity_id",
            "dimension_key",
            "observed_at",
        ),
        Index("ix_measurements_dimension", "dimension_key"),
        Index("ix_measurements_context", "context_entity_id"),
        CheckConstraint(
            "NOT (unit IS NOT NULL AND currency_code IS NOT NULL)",
            name="ck_measurements_unit_currency_xor",
        ),
        CheckConstraint(
            "currency_code IS NULL OR (length(currency_code) = 3 AND currency_code = upper(currency_code))",
            name="ck_measurements_currency_format",
        ),
        CheckConstraint(
            "length(trim(dimension_key)) > 0",
            name="ck_measurements_dimension_nonempty",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), nullable=False)
    context_entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("entities.id"), nullable=True
    )
    dimension_key: Mapped[str] = mapped_column(String(128), nullable=False)
    dimension_concept_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    numeric_value: Mapped[Decimal] = mapped_column(DecimalAsText, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    time_original_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    time_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    time_instant: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_precision: Mapped[str] = mapped_column(String(32), nullable=False, server_default="partial")
    temporal_kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="unknown")
    temporal_relation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_occurrence_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_unknown_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_interval_start: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    temporal_interval_end: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    temporal_granularity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_tense_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    temporal_source_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_input_id: Mapped[str | None] = mapped_column(ForeignKey("raw_inputs.id"), nullable=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(nullable=True)
    confidence_qualifier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)



class KnowledgeCorrectionRow(Base):
    """Epistemic Correction ledger (schema v10). Not a world-model primitive."""

    __tablename__ = "knowledge_corrections"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "target_kind",
            "target_id",
            name="uq_knowledge_corrections_target",
        ),
        Index(
            "ix_knowledge_corrections_target",
            "user_id",
            "target_kind",
            "target_id",
        ),
        Index(
            "ix_knowledge_corrections_replacement",
            "user_id",
            "replacement_kind",
            "replacement_id",
        ),
        CheckConstraint(
            "operation IN ('retract', 'replace')",
            name="ck_knowledge_corrections_operation",
        ),
        CheckConstraint(
            "target_kind IN ('event', 'measurement', 'relation', 'state', 'attribute')",
            name="ck_knowledge_corrections_target_kind",
        ),
        CheckConstraint(
            "replacement_kind IS NULL OR replacement_kind IN "
            "('event', 'measurement', 'relation', 'state', 'attribute')",
            name="ck_knowledge_corrections_replacement_kind",
        ),
        CheckConstraint(
            "("
            "operation = 'retract' AND replacement_kind IS NULL AND replacement_id IS NULL"
            ") OR ("
            "operation = 'replace' AND replacement_kind IS NOT NULL AND replacement_id IS NOT NULL"
            ")",
            name="ck_knowledge_corrections_op_replacement",
        ),
        CheckConstraint(
            "NOT ("
            "replacement_kind IS NOT NULL AND replacement_id IS NOT NULL "
            "AND target_kind = replacement_kind AND target_id = replacement_id"
            ")",
            name="ck_knowledge_corrections_no_self",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False)
    replacement_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    replacement_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_input_id: Mapped[str | None] = mapped_column(
        ForeignKey("raw_inputs.id"), nullable=True
    )
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    recorded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PrincipalBindingRow(Base):
    """Auth principal → world-model Entity (schema v11 / E1.1). Not Product identity."""

    __tablename__ = "principal_bindings"
    __table_args__ = (
        UniqueConstraint("entity_id", name="uq_principal_bindings_entity"),
        Index("ix_principal_bindings_entity", "entity_id"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
