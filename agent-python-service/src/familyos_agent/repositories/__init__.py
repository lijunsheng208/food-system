"""MySQL、Milvus 持久化接口及其实现。"""

from typing import TYPE_CHECKING, Any

from .interfaces import VectorRepository
from .milvus import MilvusCollectionManager

if TYPE_CHECKING:
    from .implementations import MySQLRepository, PGVectorRepository

__all__ = ["MilvusCollectionManager", "MySQLRepository", "PGVectorRepository", "VectorRepository", "parse_mysql_dsn"]


# __getattr__ 延迟加载数据库驱动，使领域和协议单测无需连接器也能导入。
def __getattr__(name: str) -> Any:
    if name in ("MySQLRepository", "PGVectorRepository", "parse_mysql_dsn"):
        from . import implementations

        return getattr(implementations, name)
    raise AttributeError(name)
