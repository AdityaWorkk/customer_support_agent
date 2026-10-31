from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    intent: str   # orders | billing | complaint | general | out_of_scope
