"""BGE-M3 本地 Dense/Sparse 向量生成器。"""

from typing import Sequence

from ..retrieval import EmbeddedChunks


class BGEM3EmbeddingClient:
    """使用 FlagEmbedding 的 BGE-M3 同时生成两种向量。"""

    # 加载本地模型；模型文件应在部署阶段预先下载，避免 Worker 运行时联网。
    def __init__(self, model_name: str, batch_size: int = 8, use_fp16: bool = False, device: str = "cpu") -> None:
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:
            raise RuntimeError("缺少 FlagEmbedding，请安装 BGE-M3 运行依赖") from exc
        if not model_name or batch_size <= 0:
            raise ValueError("BGE-M3 模型名和 batch_size 必须有效")
        self._batch_size = batch_size
        self._model = BGEM3FlagModel(model_name, use_fp16=use_fp16, devices=device)

    # 分批编码文本，并校验 Dense/Sparse 数量与输入顺序一致。
    def embed_documents(self, texts: Sequence[str]) -> EmbeddedChunks:
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("不能为为空文本生成向量")
        dense = []
        sparse = []
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            result = self._model.encode(batch, return_dense=True, return_sparse=True, return_colbert_vecs=False)
            batch_dense = result.get("dense_vecs")
            batch_sparse = result.get("lexical_weights")
            if batch_dense is None or batch_sparse is None or len(batch_dense) != len(batch) or len(batch_sparse) != len(batch):
                raise ValueError("BGE-M3 返回数量与文本数量不匹配")
            dense.extend(batch_dense.tolist() if hasattr(batch_dense, "tolist") else batch_dense)
            sparse.extend(batch_sparse)
        return EmbeddedChunks(dense=dense, sparse=sparse)

    # 释放模型占用的资源；FlagEmbedding 没有强制 close，因此仅清理引用。
    def close(self) -> None:
        self._model = None
