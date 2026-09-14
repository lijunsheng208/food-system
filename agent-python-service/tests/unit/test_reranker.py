"""验证 BGE Cross-Encoder 适配器的批处理和输出契约。"""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from familyos_agent.retrieval.reranker import BGEChunkReranker
from familyos_agent.retrieval.reranker import DashScopeReranker


class FakeFlagReranker:
    """模拟 FlagEmbedding Reranker 并记录分批输入。"""

    # 初始化时记录模型和设备配置。
    def __init__(self, model_name, **kwargs):
        self.model_name = model_name
        self.kwargs = kwargs
        self.calls = []

    # compute_score 按 Child 文本长度生成稳定分数。
    def compute_score(self, pairs, **kwargs):
        self.calls.append((pairs, kwargs))
        return [len(pair[1]) / 10 for pair in pairs]


class BGEChunkRerankerTest(unittest.TestCase):
    """覆盖模型延迟导入、分批计算和资源释放。"""

    # 三个候选应以 batch_size=2 分两批，并保持原输入顺序。
    def test_scores_chunks_in_batches(self):
        module = SimpleNamespace(FlagReranker=FakeFlagReranker)
        with patch.dict(sys.modules, {"FlagEmbedding": module}):
            reranker = BGEChunkReranker("reranker", batch_size=2, max_length=128)

        scores = reranker.score("问题", ["甲", "乙乙", "丙丙丙"])

        self.assertEqual(scores, [0.1, 0.2, 0.3])
        self.assertEqual(len(reranker._model.calls), 2)
        self.assertTrue(all(call[1]["normalize"] for call in reranker._model.calls))
        reranker.close()
        self.assertIsNone(reranker._model)


class FakeHTTPResponse:
    """模拟 DashScope 成功响应。"""

    # 初始化响应 JSON。
    def __init__(self, payload):
        self._payload = payload

    # 验证 HTTP 状态码。
    def raise_for_status(self):
        return None

    # 返回重排结果。
    def json(self):
        return self._payload


class FakeHTTPClient:
    """记录 DashScope 请求体并返回乱序索引结果。"""

    # 初始化请求记录。
    def __init__(self):
        self.payloads = []

    # 模拟专用 API 返回结果。
    def post(self, url, json):
        self.payloads.append((url, json))
        return FakeHTTPResponse({"output": {"results": [{"index": 1, "relevance_score": 0.2}, {"index": 0, "relevance_score": 0.9}]}})

    # 关闭客户端。
    def close(self):
        return None


class DashScopeRerankerTest(unittest.TestCase):
    """验证专用 API 的批量请求和返回索引恢复。"""

    # API 返回乱序索引时仍按原 Child 顺序返回分数。
    def test_scores_by_api_index(self):
        reranker = DashScopeReranker("https://example.test/rerank", "secret", "gte-rerank-v2", batch_size=2)
        client = FakeHTTPClient()
        reranker._client = client
        self.assertEqual(reranker.score("问题", ["甲", "乙"]), [0.9, 0.2])
        self.assertEqual(client.payloads[0][1]["input"]["documents"], ["甲", "乙"])
        reranker.close()


if __name__ == "__main__":
    unittest.main()
