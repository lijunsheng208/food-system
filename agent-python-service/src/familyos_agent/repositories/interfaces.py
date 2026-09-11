"""向量持久化边界，隔离索引编排与具体向量数据库。"""

from typing import Protocol, Sequence

from ..domain import ChildChunk


class VectorRepository(Protocol):
    """定义索引服务替换和清理单个文档版本所需的向量存储能力。"""

    # replace_version 幂等替换一个文档版本的全部子块和 Dense 向量。
    def replace_version(
        self,
        document_id: int,
        index_version: int,
        chunks: Sequence[ChildChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        ...

    # delete_version 删除未完成文档版本，供跨存储失败补偿使用。
    def delete_version(self, document_id: int, index_version: int) -> None:
        ...
