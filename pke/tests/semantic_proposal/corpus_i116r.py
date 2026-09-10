"""I11.6-R failure corpus audit — DEV reference fixtures."""

from __future__ import annotations

I116R_PROPOSAL_WIRE_AUDIT = {
    "total_proposal_wire_runs": 29,
    "provider_empty_or_no_raw": 29,
    "recoverable_transport_with_raw": 0,
    "semantic_insufficiency_with_raw": 0,
    "classification": {
        "EMPTY_RESPONSE": 29,
        "note": (
            "I11.6-R labeled these PROPOSAL_WIRE but provider_response_success=false "
            "for all 29 — no raw content preserved in benchmark rows. "
            "Primary cause: provider empty/failed response, not transport parse."
        ),
    },
    "parsed_but_no_knowledge": 14,
    "parsed_success": 25,
    "knowledge_committed": 11,
}
