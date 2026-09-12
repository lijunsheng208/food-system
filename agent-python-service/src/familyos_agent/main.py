"""FamilyOS Python 文档索引服务入口。"""

import argparse
import logging
import signal
import threading
from typing import Optional, Sequence

from .chunking import ParentChildChunker
from .agent import AgentTool, ToolRegistry, build_agent_graph, build_checkpointer, PrometheusAgentMetrics, configure_tracing
from .clients import AsyncOpenAIChatModel, BGEM3EmbeddingClient, DocumentDownloader, EmbeddingClient, LogicClient, OpenSearchRepository
from .config import load_config
from .indexing import DocumentIndexer, DocumentWorker
from .parsing import ParserRegistry
from .repositories import MilvusCollectionManager, MilvusVectorRepository, MySQLRepository
from .retrieval import MilvusHybridRetriever
from .transport.grpc.chat import AgentChatGrpcServer, ChatStreamService
from .transport.grpc.index_ingress import DocumentIndexIngressServer


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
    retriever = MilvusHybridRetriever(milvus._client, config.rag.milvus.collection, embeddings, config.rag.embedding.dimensions)
    chat_model = AsyncOpenAIChatModel(config.chat)
    async def search_knowledge(state, arguments):
        """使用服务端身份执行知识库 Hybrid 检索。"""
        import asyncio
        from .retrieval import RetrievalQuery
        rows = await asyncio.to_thread(retriever.retrieve, RetrievalQuery(str(arguments.get("query", "")), int(state["knowledge_base_id"]), int(state["user_id"]), 5))
        return [{"chunk_id": row.chunk_id, "document_id": row.document_id, "content": row.content} for row in rows]
    registry = ToolRegistry({"search_knowledge_base": AgentTool("search_knowledge_base", "检索当前用户有权限访问的知识库", search_knowledge, {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})})
    # 生产默认复用 Agent MySQL，但 checkpoint 使用独立表，避免仅依赖进程内存。
    metrics = PrometheusAgentMetrics()
    configure_tracing(config.chat.otel_endpoint)
    from prometheus_client import start_http_server
    start_http_server(config.chat.metrics_port)
    checkpointer = build_checkpointer(config.chat.checkpointer_dsn or config.database.dsn)
    chat_graph = build_agent_graph(chat_model, registry, config.chat.max_steps, config.chat.max_tool_calls, checkpointer=checkpointer, max_user_interrupts=config.chat.max_user_interrupts, metrics=metrics)
    chat_server = AgentChatGrpcServer(config.chat.port, ChatStreamService(chat_graph, config.chat.token, config.chat.timeout, mysql, metrics), mysql, config.chat.max_workers)
    opensearch = OpenSearchRepository(config.rag.opensearch) if config.rag.opensearch.enabled else None
    chunker = ParentChildChunker(config.rag.child_size, config.rag.child_overlap, config.rag.parent_size)
    indexer = DocumentIndexer(mysql, vectors, opensearch, logic, downloader, embeddings, ParserRegistry(), chunker)
    worker = DocumentWorker(mysql, logic, indexer, config.worker)
    ingress = DocumentIndexIngressServer(config.ingress.port, config.ingress.token, mysql, config.ingress.max_workers)
    stop = threading.Event()

    # 信号处理器只设置停止标志，资源关闭留在主流程执行。
    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    ingress.start()
    chat_server.start()
    try:
        worker.run(stop)
    finally:
        ingress.close()
        chat_server.close()
        milvus.close()
        if opensearch is not None:
            opensearch.close()
        embeddings.close()
        downloader.close()
        logic.close()
        # 主线程退出前关闭异步模型的 HTTP 连接池。
        import asyncio
        asyncio.run(chat_model.aclose())


if __name__ == "__main__":
    main()
