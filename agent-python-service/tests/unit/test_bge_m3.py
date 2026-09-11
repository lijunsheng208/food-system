"""BGE-M3 向量输出适配测试。"""

import unittest
from collections import defaultdict
from types import SimpleNamespace

from familyos_agent.clients.bge_m3 import BGEM3EmbeddingClient


class BGEM3EmbeddingClientTest(unittest.TestCase):
    """验证 FlagEmbedding 输出能转换为 Milvus 原生类型。"""

    # 使用伪模型验证 lexical_weights 的真实 defaultdict/字符串键格式。
    def test_normalizes_sparse_weights(self) -> None:
        client = object.__new__(BGEM3EmbeddingClient)
        client._batch_size = 8
        client._model = SimpleNamespace(
            encode=lambda *_args, **_kwargs: {
                "dense_vecs": [[0.1, 0.2]],
                "lexical_weights": [defaultdict(int, {"6": 0.25, "49125": 0.5})],
            }
        )
        result = client.embed_documents(["测试文本"])
        self.assertEqual(result.sparse, [{6: 0.25, 49125: 0.5}])


if __name__ == "__main__":
    unittest.main()
