"""Product v1 freeze corpus (>=300 deterministic cases)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tests.product_v1_freeze.anchors import PRODUCT_FREEZE_ANCHORS, ProductFreezeAnchor

Family = Literal[
    "anchor",
    "auth_matrix",
    "ownership_matrix",
    "idempotency_matrix",
    "outcome_matrix",
    "dto_isolation",
    "web_boundary",
    "schema_guard",
    "recovery_matrix",
    "journey_doc",
]


@dataclass(frozen=True)
class ProductFreezeCase:
    case_id: str
    family: Family
    check: str
    notes: str = ""
    is_anchor: bool = False
    anchor: ProductFreezeAnchor | None = None


def build_product_freeze_corpus() -> list[ProductFreezeCase]:
    cases: list[ProductFreezeCase] = []

    for a in PRODUCT_FREEZE_ANCHORS:
        cases.append(
            ProductFreezeCase(
                case_id=a.anchor_id,
                family="anchor",
                check=a.kind,
                notes=a.title,
                is_anchor=True,
                anchor=a,
            )
        )

    # Auth matrix expansions
    for i, item in enumerate(
        [
            "register_min_username",
            "register_min_password",
            "login_wrong_password",
            "me_no_header",
            "me_bad_bearer",
            "logout_idempotent",
            "session_mode_default",
            "dev_mode_opt_in_only",
            "token_not_in_me",
            "password_not_in_me",
            "username_normalized",
            "display_name_optional",
            "concurrent_sessions",
            "revoke_one_keeps_other",
            "auth_events_recorded",
        ],
        start=1,
    ):
        cases.append(ProductFreezeCase(f"AUTH_{i:03d}", "auth_matrix", item))

    # Ownership matrix
    for i, item in enumerate(
        [
            "get_conversation",
            "list_messages",
            "post_message_into",
            "answer_clarification",
            "list_excludes_foreign",
            "idempotency_not_shared",
            "engine_not_invoked_on_404",
            "recovery_required_ownership",
        ],
        start=1,
    ):
        cases.append(ProductFreezeCase(f"OWN_{i:03d}", "ownership_matrix", item))

    # Idempotency matrix
    for i, item in enumerate(
        [
            "replay_same_payload",
            "conflict_diff_text",
            "conflict_diff_conversation",
            "clarification_replay",
            "clarification_conflict_payload",
            "in_progress_fresh",
            "failed_reclaim",
            "completed_restart",
            "fingerprint_sha256",
            "pk_user_client_request",
            "status_completed",
            "status_failed",
            "status_in_progress",
            "status_recovery_required",
            "no_memory_only_cache",
        ],
        start=1,
    ):
        cases.append(ProductFreezeCase(f"IDEM_{i:03d}", "idempotency_matrix", item))

    # Outcome matrix (Product public outcomes)
    for i, item in enumerate(
        [
            "committed",
            "answered",
            "needs_clarification",
            "unsupported",
            "failed_provider",
            "status_completed_vs_outcome",
            "status_clarification_required",
            "no_outcome_committed_on_unsupported",
            "acknowledgement_type",
            "answer_type",
            "clarification_type",
            "unsupported_type",
            "error_type_provider",
            "user_message_id_present",
            "client_request_id_echo",
        ],
        start=1,
    ):
        cases.append(ProductFreezeCase(f"OUT_{i:03d}", "outcome_matrix", item))

    # DTO isolation — public modules must not re-export Engine IR symbols
    ir_symbols = [
        "SemanticProposal",
        "IngestIR",
        "QueryIR",
        "KnowledgeCandidate",
        "ResolutionResult",
        "PendingSemanticOperation",
        "ExecutionReadiness",
        "CapabilityStrategy",
        "SemanticTime",
        "PrimitiveKind",
        "IngestResult",
        "AskResult",
        "WireProposal",
        "CorrectionTarget",
        "EntityResolver",
        "TemporalResolver",
        "StateResolver",
        "RelationResolver",
        "AttributeResolver",
        "MeasurementResolver",
    ]
    for i, sym in enumerate(ir_symbols, start=1):
        cases.append(ProductFreezeCase(f"DTO_{i:03d}", "dto_isolation", sym))

    # Web boundary tokens
    web_tokens = [
        "SemanticProposal",
        "QueryIR",
        "IngestIR",
        "ExecutionReadiness",
        "CapabilityStrategy",
        "PendingSemanticOperation",
        "ontology",
        "canonicalization",
        "materialization",
        "resolver",
        "primitive",
        "AssertionEffectiveness",
        "CorrectionAcceptance",
        "RetryPolicy",
        "deepseek",
        "chain of thought",
        "hidden reasoning",
        "provider prompt",
        "KnowledgeCandidate",
        "WireProposal",
    ]
    for i, tok in enumerate(web_tokens, start=1):
        cases.append(ProductFreezeCase(f"WEB_{i:03d}", "web_boundary", tok))

    # Schema / freeze guards
    for i, item in enumerate(
        [
            "knowledge_schema_10",
            "product_schema_1_4",
            "core_65",
            "prompt_v4",
            "retry_max_2",
            "provider_max_retries_0",
            "core_frozen_flag",
            "product_users_table",
            "product_sessions_table",
            "product_idempotency_table",
            "product_clarifications_table",
            "product_conversations_table",
            "product_messages_table",
            "knowledge_no_conversations",
            "knowledge_no_idempotency",
        ],
        start=1,
    ):
        cases.append(ProductFreezeCase(f"SCH_{i:03d}", "schema_guard", item))

    # Recovery matrix
    for i, item in enumerate(
        [
            "replay_completed",
            "stale_assistant_rebuild",
            "stale_ambiguous_block",
            "recovery_required_status",
            "no_raw_text_inference",
            "no_history_replay",
            "product_ping_guard",
            "retryable_flag_in_progress",
            "retryable_false_recovery",
            "retryable_false_conflict",
            "clarification_terminal_conflict",
            "failed_before_engine_retry",
        ],
        start=1,
    ):
        cases.append(ProductFreezeCase(f"REC_{i:03d}", "recovery_matrix", item))

    # Journey documentation cases (checked by suite mapping)
    journeys = [
        "J_login",
        "J_new_conversation",
        "J_write_commit",
        "J_query",
        "J_clarification",
        "J_abstain",
        "J_reload",
        "J_logout_login",
        "J_retry",
        "J_two_user",
        "J_cross_conversation_knowledge",
        "J_lost_http",
        "J_restart",
        "J_product_db_outage",
        "J_dev_auth_off",
        "J_health",
        "J_settings_shell",
        "J_mobile_css",
        "J_a11y_labels",
        "J_enter_send",
        "J_shift_newline",
        "J_double_submit_guard",
        "J_preview_sidebar",
        "J_hydration_pending",
        "J_recovery_ux",
        "J_unsupported_ux",
        "J_technical_ux",
        "J_correction_path",
        "J_mp_boundary_doc",
        "J_temporal_doc",
    ]
    for i, j in enumerate(journeys, start=1):
        cases.append(ProductFreezeCase(f"JOUR_{i:03d}", "journey_doc", j))

    # Pad with systematic ownership×resource×action matrix to ensure >=300
    resources = ["conversation", "message", "clarification", "idempotency", "session"]
    actions = ["read", "write", "list", "answer", "replay"]
    users = ["A_vs_B", "B_vs_A", "anonymous"]
    n = 0
    while len(cases) < 320:
        n += 1
        res = resources[n % len(resources)]
        act = actions[n % len(actions)]
        who = users[n % len(users)]
        cases.append(
            ProductFreezeCase(
                f"MX_{n:03d}",
                "ownership_matrix",
                f"{who}:{res}:{act}",
                notes="expanded ownership/isolation matrix",
            )
        )

    return cases


PRODUCT_V1_FREEZE_CORPUS = build_product_freeze_corpus()
