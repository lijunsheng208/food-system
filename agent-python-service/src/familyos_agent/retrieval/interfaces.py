"""混合检索应用边界及稳定的输入输出模型。"""

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol, Sequence


@dataclass(frozen=True)
class RetrievalQuery:
    """描述一次经过权限限定的知识库混合检索请求。"""

    text: str
    knowledge_base_id: int
    user_id: int
    top_k: int
    document_ids: Sequence[int] = ()


@dataclass(frozen=True)
class RetrievedChunk:
    """描述 Hybrid Retriever 返回给 Agent 的可引用文档块。"""

    chunk_id: str
    document_id: int
    knowledge_base_id: int
    index_version: int
    parent_id: str
    content: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddedChunks:
    """描述 BGE-M3 为同一批文本生成的 Dense 与 Sparse 向量。"""

    dense: Sequence[Sequence[float]]
    sparse: Sequence[Dict[int, float]]


class HybridRetriever(Protocol):
    """定义 Agent 所依赖的 Dense/Sparse 融合检索能力。"""

    # retrieve 在调用方权限和活动版本约束内返回按相关性排序的文档块。
    def retrieve(self, query: RetrievalQuery) -> Sequence[RetrievedChunk]:
        ...
