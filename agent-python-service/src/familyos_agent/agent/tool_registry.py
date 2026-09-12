"""D1 Agent Tool 白名单和调用边界。"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping

from .state import AgentState


@dataclass(frozen=True)
class AgentTool:
    """描述一个由服务端注册、模型只能选择不能修改的业务 Tool。"""

    name: str
    description: str
    handler: Callable[[AgentState, Mapping[str, Any]], Any]
    parameters: Mapping[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """管理 Agent 可调用的固定 Tool 集合，并拒绝未知 Tool。"""

    def __init__(self, tools: Mapping[str, AgentTool]) -> None:
        if not tools or any(name != tool.name for name, tool in tools.items()):
            raise ValueError("Tool Registry 配置无效")
        self._tools = dict(tools)

    # 返回给模型的 Tool 描述，不暴露服务端权限字段和内部对象。
    def definitions(self) -> list[Dict[str, Any]]:
        return [{"type": "function", "function": {"name": tool.name, "description": tool.description, "parameters": dict(tool.parameters)}} for tool in self._tools.values()]

    # 根据模型选择获取 Tool，未知名称必须快速失败而不是静默降级。
    def get(self, name: str) -> AgentTool:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError("未知 Agent Tool: %s" % name)
        return tool


def decode_tool_arguments(value: Any) -> Dict[str, Any]:
    """严格解析模型返回的 JSON Tool 参数，拒绝非对象和非法 JSON。"""
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str):
        raise ValueError("Tool 参数必须是 JSON 对象")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("Tool 参数 JSON 无效") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Tool 参数必须是 JSON 对象")
    return parsed

