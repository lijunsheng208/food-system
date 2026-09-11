"""验证阶段 A 新增 Milvus 配置的边界校验。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from familyos_agent.config import load_config


VALID_CONFIG = """
database: {dsn: 'u:p@tcp(127.0.0.1:3306)/familyos_agent'}
rocketmq: {endpoint: '127.0.0.1:9876'}
logic: {target: '127.0.0.1:50051', agent_token: 'internal-token'}
rag:
  embedding: {api_key: 'embedding-key', model: 'embedding-model', dimensions: 4}
  milvus: {uri: 'http://127.0.0.1:19530', database: 'default', collection: 'familyos_document_chunks_v1'}
"""


class ConfigTest(unittest.TestCase):
    """确保 Milvus 必填配置和固定 v1 契约在启动前失败。"""

    # 写入临时配置并清空 FAMILYOS_AGENT_ 覆盖，保证测试只验证文件内容。
    def _load(self, content: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(content, encoding="utf-8")
            clean_environment = {key: value for key, value in os.environ.items() if not key.startswith("FAMILYOS_AGENT_")}
            with patch.dict(os.environ, clean_environment, clear=True):
                return load_config(str(path))

    # 合法配置应生成固定名称且使用 COSINE 的 Milvus 配置。
    def test_loads_milvus_config(self) -> None:
        config = self._load(VALID_CONFIG)
        self.assertEqual(config.rag.milvus.collection, "familyos_document_chunks_v1")
        self.assertEqual(config.rag.milvus.dense_metric_type, "COSINE")

    # 空 URI 属于外部系统边界错误，服务不得带缺失配置启动。
    def test_rejects_missing_milvus_uri(self) -> None:
        with self.assertRaisesRegex(ValueError, "Milvus"):
            self._load(VALID_CONFIG.replace("http://127.0.0.1:19530", ""))


if __name__ == "__main__":
    unittest.main()
