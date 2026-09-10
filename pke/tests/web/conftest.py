from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import make_client, register_user
from tests.integration.test_ask import RAW_F, _query_ir
from tests.integration.test_ingest import (
    RAW_A,
    RAW_D1,
    RAW_E,
    RAW_NO_TIME,
    ir_a,
    ir_d1,
    ir_e,
    ir_negative,
    ir_no_time,
)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return make_client(
        tmp_path,
        {
            RAW_A: ir_a(),
            RAW_NO_TIME: ir_no_time(),
            "Troquei o óleo do Corolla. hoje": ir_a("Troquei o óleo do Corolla. hoje"),
            RAW_D1: ir_d1(),
            RAW_E: ir_e(),
            RAW_F: _query_ir(),
            "Troquei o óleo do Corolla hoje por -320 reais.": ir_negative(),
        },
    )


@pytest.fixture
def auth(client: TestClient) -> dict[str, str]:
    return register_user(client, "alice", "password123")
