import pytest


@pytest.fixture(autouse=True)
def _clear_learned_attribute_overlay() -> None:
    from pke.interpretation.semantic.attribute_registry import clear_learned_dimensions

    clear_learned_dimensions()
    yield
    clear_learned_dimensions()
