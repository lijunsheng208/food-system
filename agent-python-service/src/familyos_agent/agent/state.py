"""D1 LangGraph Agent 的可序列化状态。"""

from typing import Any, Dict, List, TypedDict


class AgentState(TypedDict, total=False):
    """保存 Agent 单次运行状态，避免把模型和外部连接放入 Graph State。"""

    user_id: int
    knowledge_base_id: int
    conversation_id: str
    request_id: str
    original_query: str
    rewritten_query: str
    messages: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    documents: List[Any]
    citations: List[Dict[str, Any]]
    answer: str
    agent_steps: int
    tool_call_count: int
    pending_tool_name: str
    pending_tool_arguments: Any
    terminal_status: str
    error_code: str
    error_message: str
