"""MySQL、Milvus 持久化接口及其实现。"""

from typing import TYPE_CHECKING, Any

from .interfaces import VectorRepository
from .milvus import MilvusCollectionManager, MilvusVectorRepository
from .semantic_memory import MilvusSemanticMemoryRepository

if TYPE_CHECKING:
    from .implementations import MySQLRepository

__all__ = ["MilvusCollectionManager", "MilvusVectorRepository", "MilvusSemanticMemoryRepository", "MySQLRepository", "VectorRepository", "parse_mysql_dsn"]


# __getattr__ 延迟加载数据库驱动，使领域和协议单测无需连接器也能导入。
def __getattr__(name: str) -> Any:
    if name in ("MySQLRepository", "parse_mysql_dsn"):
        from . import implementations

        return getattr(implementations, name)
    raise AttributeError(name)
