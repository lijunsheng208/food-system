"""FamilyOS Python 文档索引服务入口。"""

import argparse
import logging
import signal
import threading
from typing import Optional, Sequence

from .chunking import ParentChildChunker
from .clients import BGEM3EmbeddingClient, DocumentDownloader, EmbeddingClient, LogicClient, OpenSearchRepository
from .config import load_config
from .indexing import DocumentIndexer, DocumentWorker
from .messaging import RocketMQDocumentConsumer
from .parsing import ParserRegistry
from .repositories import MilvusCollectionManager, MilvusVectorRepository, MySQLRepository


# 组装 Consumer 和索引 Worker，并在退出信号后按顺序释放连接。
def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="FamilyOS Python 文档索引服务")
    parser.add_argument("--config", default=None, help="配置文件路径")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = load_config(args.config)
    mysql = MySQLRepository(config.database.dsn)
    milvus = MilvusCollectionManager(config.rag.milvus, config.rag.embedding.dimensions)
    milvus.ensure_ready()
    vectors = MilvusVectorRepository(milvus)
    logic = LogicClient(config.logic)
    downloader = DocumentDownloader(config.rag.max_file_size, config.rag.download_timeout)
    if config.rag.embedding.provider == "bge-m3":
        embeddings = BGEM3EmbeddingClient(config.rag.embedding.model_name, config.rag.embedding.batch_size, config.rag.embedding.use_fp16, config.rag.embedding.device)
    else:
        raise ValueError("阶段 B 仅支持 embedding.provider=bge-m3")
    opensearch = OpenSearchRepository(config.rag.opensearch) if config.rag.opensearch.enabled else None
    chunker = ParentChildChunker(config.rag.child_size, config.rag.child_overlap, config.rag.parent_size)
    indexer = DocumentIndexer(mysql, vectors, opensearch, logic, downloader, embeddings, ParserRegistry(), chunker)
    worker = DocumentWorker(mysql, logic, indexer, config.worker)
    consumer = RocketMQDocumentConsumer(config.rocketmq, mysql)
    stop = threading.Event()

    # 信号处理器只设置停止标志，资源关闭留在主流程执行。
    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    consumer.start()
    try:
        worker.run(stop)
    finally:
        consumer.close()
        milvus.close()
        if opensearch is not None:
            opensearch.close()
        embeddings.close()
        downloader.close()
        logic.close()


if __name__ == "__main__":
    main()
