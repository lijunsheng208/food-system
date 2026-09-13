"""图实体抽取使用的 OpenAI-compatible 同步模型客户端。"""

from typing import Any

import httpx


class SyncOpenAIModel:
    """为索引 Worker 提供同步结构化 LLM 调用。"""

    # 初始化兼容 OpenAI Chat Completions 的连接参数。
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float, max_tokens: int) -> None:
        if not base_url or not api_key or not model or timeout <= 0 or max_tokens <= 0:
            raise ValueError("图抽取模型配置不完整")
        self._url, self._key, self._model, self._timeout, self._max_tokens = base_url.rstrip("/") + "/chat/completions", api_key, model, timeout, max_tokens

    # 同步调用一次抽取请求，返回 LLMGraphExtractor 所需的 content 字段。
    def invoke(self, messages: list[dict[str, str]]) -> dict[str, str]:
        response = httpx.post(self._url, headers={"Authorization": "Bearer " + self._key}, json={"model": self._model, "messages": messages, "temperature": 0, "max_tokens": self._max_tokens, "response_format": {"type": "json_object"}}, timeout=self._timeout)
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        return {"content": str(body["choices"][0]["message"].get("content", ""))}
