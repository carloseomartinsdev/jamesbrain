from jamescore.tooling.registry import ToolRegistry


def test_tool_registry_empty_in_j11():
    registry = ToolRegistry()
    assert registry.registered_count() == 0
    assert registry.list_contracts() == []
    assert registry.get("weather") is None
    assert registry.find_by_capability("weather") is None


def test_pke_is_not_a_registered_tool():
    registry = ToolRegistry()
    assert registry.get("pke") is None
    assert registry.find_by_capability("personal_knowledge") is None
    assert registry.find_by_capability("pke") is None


def test_dispatch_refuses_empty_registry():
    registry = ToolRegistry()
    try:
        registry.dispatch("weather", {})
        raise AssertionError("dispatch must fail")
    except RuntimeError as exc:
        assert "empty" in str(exc).lower()
