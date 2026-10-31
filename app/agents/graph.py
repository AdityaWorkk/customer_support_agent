from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agents import nodes
from app.agents.state import AgentState
from app.agents.tools import ALL_TOOLS
from app.core.config import settings
from app.core.database import get_sync_client

_checkpointer: MongoDBSaver | None = None
_chat_graph = None


def get_checkpointer() -> MongoDBSaver:
    global _checkpointer
    if _checkpointer is None:
        # Official library checkpointer. Sync client; its async methods run in a thread pool.
        _checkpointer = MongoDBSaver(get_sync_client(), db_name=settings.DATABASE_NAME,
                                     checkpoint_collection_name="lg_checkpoints",
                                     writes_collection_name="lg_checkpoint_writes")
    return _checkpointer


def build_chat_graph(checkpointer=None):
    g = StateGraph(AgentState)
    g.add_node("classify", nodes.classify)
    g.add_node("out_of_scope", nodes.out_of_scope)
    g.add_node("agent", nodes.agent)
    g.add_node("tools", ToolNode(ALL_TOOLS, handle_tool_errors=True))
    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", nodes.route_after_classify, {"out_of_scope": "out_of_scope", "agent": "agent"})
    g.add_edge("out_of_scope", END)
    g.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    g.add_edge("tools", "agent")
    return g.compile(checkpointer=checkpointer or get_checkpointer())


def get_chat_graph():
    global _chat_graph
    if _chat_graph is None:
        _chat_graph = build_chat_graph()
    return _chat_graph
