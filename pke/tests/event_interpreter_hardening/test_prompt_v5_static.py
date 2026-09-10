"""I12.8 static prompt contract tests (pre-live)."""

from __future__ import annotations

import re

from pke.interpretation import prompts_v4, prompts_v5


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold())


def test_v5_version_identity() -> None:
    assert prompts_v5.PROMPT_VERSION == "pke.interpret.v5-event"


def test_v4_unchanged_as_control() -> None:
    assert prompts_v4.PROMPT_VERSION == "pke.interpret.v4"
    assert "Medi a temperatura e deu 95°C." in prompts_v4.SYSTEM_PROMPT


def test_v5_coexistence_rule_present() -> None:
    text = _norm(prompts_v5.SYSTEM_PROMPT)
    assert "event e measurement" in text or "event e measurement como assertions" in text
    assert "aditivas" in text or "aditivas independentes" in text


def test_v5_measurement_does_not_erase_event() -> None:
    text = _norm(prompts_v5.SYSTEM_PROMPT)
    assert "não substitui" in text and "elimina event" in text


def test_v5_measurement_alone_does_not_imply_event() -> None:
    text = _norm(prompts_v5.SYSTEM_PROMPT)
    assert "só measurement" in text or "measurement only" in text
    assert "não emita event" in text


def test_v5_no_verb_catalog_expansion() -> None:
    """v5 must not add verb→Event enumeration beyond v4 examples."""
    v4_examples = prompts_v4.SYSTEM_PROMPT.count("→ Event")
    v5_examples = prompts_v5.SYSTEM_PROMPT.count("→ Event")
    assert v5_examples <= v4_examples + 1


def test_v5_no_actor_heuristic() -> None:
    text = _norm(prompts_v5.SYSTEM_PROMPT)
    assert "humano vs sensor" in text or "sujeito humano vs sensor" in text
    assert "human subject" not in text


def test_prompt_size_delta_bounded() -> None:
    v4_len = len(prompts_v4.SYSTEM_PROMPT)
    v5_len = len(prompts_v5.SYSTEM_PROMPT)
    delta = v5_len - v4_len
    delta_pct = 100.0 * delta / v4_len
    assert delta_pct < 9.0, f"delta {delta_pct:.1f}% too large"
    assert 200 <= delta <= 500, f"unexpected delta chars={delta}"


def test_v5_preserves_v4_few_shots_via_import() -> None:
    from pke.interpretation.prompts_v5 import FEW_SHOT_EVENT_PLUS_MEASUREMENT

    assert FEW_SHOT_EVENT_PLUS_MEASUREMENT["ir"]["raw_input"].startswith("Medi a temperatura")
