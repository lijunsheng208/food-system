"""本地 BGE 和 DashScope 专用 Rerank API 重排客户端。"""

from math import isfinite
from typing import Any, Sequence

import httpx


class BGEChunkReranker:
    """使用 FlagEmbedding 的 BGE Reranker 对 Query-Child 文本对打分。"""

    # 初始化本地模型；部署时应提前准备模型文件，避免线上启动期间下载。
    def __init__(self, model_name: str, batch_size: int = 16, max_length: int = 512, use_fp16: bool = False, device: str = "cpu") -> None:
        if not model_name or batch_size <= 0 or max_length <= 0:
            raise ValueError("BGE Reranker 配置无效")
        try:
            from FlagEmbedding import FlagReranker
        except ImportError as exc:
            raise RuntimeError("缺少 FlagEmbedding，请安装 Cross-Encoder 运行依赖") from exc
        self._batch_size = batch_size
        self._max_length = max_length
        self._model: Any = FlagReranker(model_name, use_fp16=use_fp16, devices=device)

    # score 分批计算 Query-Child 相关性，并校验第三方模型返回的数量和数值。
    def score(self, query: str, chunks: Sequence[str]) -> Sequence[float]:
        if not query.strip() or not chunks or any(not text.strip() for text in chunks):
            raise ValueError("Cross-Encoder 输入不能为空")
        scores = []
        for start in range(0, len(chunks), self._batch_size):
            batch = chunks[start : start + self._batch_size]
            result = self._model.compute_score(
                [[query, text] for text in batch],
                batch_size=self._batch_size,
                max_length=self._max_length,
                normalize=True,
            )
            values = result.tolist() if hasattr(result, "tolist") else result
            if not isinstance(values, (list, tuple)):
                values = [values]
            scores.extend(float(value) for value in values)
        if len(scores) != len(chunks) or any(not isfinite(value) for value in scores):
            raise ValueError("Cross-Encoder 返回的分数数量或数值无效")
        return scores

    # close 释放模型引用，便于服务退出时回收 CPU/GPU 资源。
    def close(self) -> None:
        self._model = None


class DashScopeReranker:
    """调用 DashScope 专用文本重排 API，避免使用对话模型模拟排序。"""

    # 初始化 API 客户端和模型参数，密钥只保存在进程内存中。
    def __init__(self, base_url: str, api_key: str, model_name: str, timeout: float = 30.0, batch_size: int = 16) -> None:
        if not base_url or not api_key or not model_name or timeout <= 0 or batch_size <= 0:
            raise ValueError("DashScope Reranker 配置无效")
        self._url = base_url.rstrip("/") + ("/reranks" if base_url.rstrip("/").endswith("/v1") else "")
        self._model, self._timeout, self._batch_size = model_name, timeout, batch_size
        self._client = httpx.Client(timeout=timeout, headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})

    # score 分批调用专用 Rerank API，并按原候选顺序恢复相关性分数。
    def score(self, query: str, chunks: Sequence[str]) -> Sequence[float]:
        if not query.strip() or not chunks or any(not text.strip() for text in chunks):
            raise ValueError("DashScope Reranker 输入不能为空")
        scores = []
        for start in range(0, len(chunks), self._batch_size):
            batch = list(chunks[start : start + self._batch_size])
            # Workspace 兼容接口使用 OpenAI 风格的 query/documents；原生接口使用 input/parameters。
            body = ({"model": self._model, "query": query, "documents": batch, "top_n": len(batch)}
                    if self._url.endswith("/reranks") else
                    {"model": self._model, "input": {"query": query, "documents": batch}, "parameters": {"return_documents": False}})
            response = self._client.post(self._url, json=body)
            response.raise_for_status()
            payload = response.json()
            results = []
            if isinstance(payload, dict):
                results = payload.get("results") or ((payload.get("output") or {}).get("results") or [])
            if len(results) != len(batch):
                raise RuntimeError("DashScope Reranker 返回数量与候选数量不一致")
            ordered = sorted(results, key=lambda item: int(item.get("index", -1)))
            if [int(item.get("index", -1)) for item in ordered] != list(range(len(batch))):
                raise RuntimeError("DashScope Reranker 返回索引无效")
            scores.extend(float(item["relevance_score"]) for item in ordered)
        return scores

    # close 关闭 HTTP 连接池，避免服务退出时遗留连接。
    def close(self) -> None:
        self._client.close()
