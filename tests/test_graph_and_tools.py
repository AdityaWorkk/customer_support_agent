"""Offline checks: graph compiles, routing heuristics, tool schemas hide injected config."""
from langgraph.checkpoint.memory import InMemorySaver

from app.agents import nodes
from app.agents.graph import build_chat_graph
from app.agents.tools import ALL_TOOLS, TOOLSETS


def test_graph_compiles():
    g = build_chat_graph(InMemorySaver())
    assert {"classify", "agent", "tools", "out_of_scope"} <= set(g.get_graph().nodes)


def test_heuristics():
    h = nodes._heuristic
    assert h("where is my order ORD-10003?", None) == "orders"
    assert h("I want to cancel ORD-10001 and get a refund", None) == "billing"
    assert h("my headphones arrived broken", None) == "complaint"
    assert h("what is the capital of France", None) is None
    assert h("yes", "billing") == "billing"


def test_tools_never_expose_user_id_or_config():
    for t in ALL_TOOLS:
        props = set(t.args)
        assert "user_id" not in props and "config" not in props, t.name


def test_toolsets_are_subsets():
    names = {t.name for t in ALL_TOOLS}
    for tools in TOOLSETS.values():
        assert {t.name for t in tools} <= names
