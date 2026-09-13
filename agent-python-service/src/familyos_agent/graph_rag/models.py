"""图 RAG 的稳定领域模型；本阶段只定义契约，不连接 Neo4j。"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class GraphQueryType(str, Enum):
    """限制在线图查询的类型，避免模型自由生成查询语义。"""

    ENTITY_RELATION = "entity_relation"
    MULTI_HOP = "multi_hop"
    SUBGRAPH = "subgraph"
    PATH_FINDING = "path_finding"


ALLOWED_RELATION_TYPES = frozenset(
    {
        "REQUIRES",
        "CONTAINS_STEP",
        "BELONGS_TO_CATEGORY",
        "SUITABLE_FOR",
        "PAIRS_WITH",
        "PRECEDES",
    }
)


@dataclass(frozen=True)
class GraphEntity:
    """描述一个带权限、版本和原文来源的图实体。"""

    entity_id: str
    entity_type: str
    name: str
    user_id: int
    knowledge_base_id: int
    document_id: int
    index_version: int
    source_chunk_id: str
    source_page: Optional[str] = None
    confidence: float = 1.0
    status: str = "active"
    aliases: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class GraphRelation:
    """描述两个实体之间可追溯且受白名单约束的关系。"""

    relation_id: str
    relation_type: str
    source_entity_id: str
    target_entity_id: str
    user_id: int
    knowledge_base_id: int
    document_id: int
    index_version: int
    source_chunk_id: str
    source_page: Optional[str] = None
    confidence: float = 1.0
    status: str = "active"

    # 校验关系类型，防止抽取模型写入未定义的业务关系。
    def __post_init__(self) -> None:
        if self.relation_type not in ALLOWED_RELATION_TYPES:
            raise ValueError("不支持的图关系类型: %s" % self.relation_type)


@dataclass(frozen=True)
class GraphQueryPlan:
    """保存 LLM 规划后的受控图查询参数，不包含可执行 Cypher。"""

    query_type: GraphQueryType
    source_entities: List[str]
    target_entities: List[str] = field(default_factory=list)
    relation_types: List[str] = field(default_factory=list)
    max_depth: int = 2
    max_nodes: int = 50
    filters: Dict[str, Any] = field(default_factory=dict)

    # 校验遍历边界和关系白名单，避免查询计划放大资源消耗或越过业务边界。
    def __post_init__(self) -> None:
        if not self.source_entities:
            raise ValueError("图查询至少需要一个源实体")
        if self.max_depth <= 0 or self.max_depth > 3:
            raise ValueError("图查询深度必须在 1 到 3 之间")
        if self.max_nodes <= 0 or self.max_nodes > 200:
            raise ValueError("图查询节点数必须在 1 到 200 之间")
        unsupported = set(self.relation_types) - ALLOWED_RELATION_TYPES
        if unsupported:
            raise ValueError("图查询包含不支持的关系类型: %s" % ",".join(sorted(unsupported)))


@dataclass(frozen=True)
class Evidence:
    """统一描述文档、图结果或 Tool 返回的可审计回答证据。"""

    source_type: str
    content: str
    user_id: int
    knowledge_base_id: int
    document_id: Optional[int] = None
    chunk_id: Optional[str] = None
    source_page: Optional[str] = None
    graph_path: Optional[str] = None
    index_version: Optional[int] = None
    confidence: float = 1.0

    # 校验来源类型，保证后续引用处理可以按统一契约分流。
    def __post_init__(self) -> None:
        if self.source_type not in {"document", "graph", "tool"}:
            raise ValueError("不支持的证据来源类型: %s" % self.source_type)
        if not self.content.strip():
            raise ValueError("证据内容不能为空")
