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
from .retrieval import BGEChunkReranker, DashScopeReranker, HybridRetriever, MilvusHybridRetriever, MilvusParentChildRetriever
from .graph_rag import ControlledRetriever, LLMGraphExtractor, LLMIntentClassifier
from .graph_rag.llm_client import SyncOpenAIModel
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
    base_retriever = MilvusHybridRetriever(milvus._client, config.rag.milvus.collection, embeddings, config.rag.embedding.dimensions, config.rag.milvus.rrf_k, config.rag.milvus.candidate_limit)
    reranker = None
    retriever: HybridRetriever = base_retriever
    if config.rag.reranker.enabled:
        # 父子检索只在显式启用时加载本地 Cross-Encoder，避免未准备模型的环境启动时联网。
        reranker = (BGEChunkReranker(config.rag.reranker.model_name, config.rag.reranker.batch_size, config.rag.reranker.max_length, config.rag.reranker.use_fp16, config.rag.reranker.device)
                    if config.rag.reranker.provider == "local" else
                    DashScopeReranker(config.rag.reranker.base_url, config.rag.reranker.api_key, config.rag.reranker.model_name, config.rag.reranker.timeout, config.rag.reranker.batch_size))
        retriever = MilvusParentChildRetriever(base_retriever, milvus._client, config.rag.milvus.collection, reranker, config.rag.reranker.recall_top_k)
    # 阶段 4 先启用内部受控路由；未配置 Neo4j 时自动退化为 Milvus 检索。
    graph_driver = None
    graph_repository = None
    if config.graph_retrieval.enabled:
        try:
            from neo4j import GraphDatabase
            graph_driver = GraphDatabase.driver(config.graph_retrieval.uri, auth=(config.graph_retrieval.user, config.graph_retrieval.password))
            graph_driver.verify_connectivity()
            from .graph_rag import Neo4jGraphRepository, GraphRetriever
            graph_repository = Neo4jGraphRepository(graph_driver)
        except Exception:
            logging.getLogger(__name__).exception("Neo4j 初始化失败，阶段 4 回退到 Milvus")
            if graph_driver is not None:
                graph_driver.close()
                graph_driver = None
    graph_retriever = GraphRetriever(graph_repository, mysql.resolve_chunks) if graph_repository is not None else None
    intent_classifier = None
    if config.graph_extraction.enabled:
        # 意图分类复用已验证的 OpenAI-compatible 配置，统一生成 RetrievalPlan。
        intent_model = SyncOpenAIModel(config.graph_extraction.base_url, config.graph_extraction.api_key, config.graph_extraction.model, config.graph_extraction.timeout, config.graph_extraction.max_tokens)
        intent_classifier = LLMIntentClassifier(intent_model).classify
    controlled_retriever = ControlledRetriever(retriever, graph_retriever, timeout=config.graph_retrieval.timeout, intent_classifier=intent_classifier)
    graph_extractor = None
    if graph_repository is not None and config.graph_extraction.enabled:
        graph_extractor = LLMGraphExtractor(SyncOpenAIModel(config.graph_extraction.base_url, config.graph_extraction.api_key, config.graph_extraction.model, config.graph_extraction.timeout, config.graph_extraction.max_tokens), config.graph_extraction.confidence_threshold).extract
    chat_model = AsyncOpenAIChatModel(config.chat)
    rewrite_model = None
    if config.chat.enable_query_rewrite:
        # 查询改写的 JSON 是内部中间结果，禁止通过 LangGraph 流式回调发送给客户端。
        rewrite_model = AsyncOpenAIChatModel(type("RewriteConfig", (), {"base_url": config.chat.rewrite_base_url, "api_key": config.chat.rewrite_api_key, "model": config.chat.rewrite_model, "timeout": config.chat.rewrite_timeout, "max_tokens": config.chat.rewrite_max_tokens})(), enable_streaming=False)
    async def search_knowledge(state, arguments):
        """使用服务端身份执行知识库 Hybrid 检索。"""
        import asyncio
        import json
        from .retrieval import RetrievalQuery
        rows = await asyncio.to_thread(retriever.retrieve, RetrievalQuery(str(arguments.get("query", "")), int(state["knowledge_base_id"]), int(state["user_id"]), 5))
        return json.dumps({"documents": [{"chunk_id": row.chunk_id, "document_id": row.document_id, "content": row.content} for row in rows]}, ensure_ascii=False)

    async def get_user_dietary_preferences(state, _arguments):
        """使用服务端认证身份查询当前用户保存的个人饮食偏好。"""
        import asyncio
        import json
        type_names = {1: "口味", 2: "菜系", 3: "饮食习惯", 4: "忌口食材", 5: "过敏食材"}
        rows = await asyncio.to_thread(logic.list_dietary_preferences, int(state["user_id"]))
        preferences = [{**row, "preference_type_name": type_names.get(int(row["preference_type"]), "未知类型")} for row in rows]
        return json.dumps({"preferences": preferences}, ensure_ascii=False)

    registry = ToolRegistry({
        "search_knowledge_base": AgentTool("search_knowledge_base", "检索当前用户有权限访问的知识库。需要菜谱步骤、用量、时间、温度或文档事实时调用。", search_knowledge, {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
        "get_user_dietary_preferences": AgentTool("get_user_dietary_preferences", "查询当前用户已保存的口味、菜系、饮食习惯、忌口和过敏信息。进行个性化菜谱推荐、菜单规划、食材替换或饮食适配判断前必须调用。", get_user_dietary_preferences, {"type": "object", "properties": {}, "additionalProperties": False}),
    })
    # 生产默认复用 Agent MySQL，但 checkpoint 使用独立表，避免仅依赖进程内存。
    metrics = PrometheusAgentMetrics()
    configure_tracing(config.chat.otel_endpoint)
    from prometheus_client import start_http_server
    start_http_server(config.chat.metrics_port)
    checkpointer = build_checkpointer(config.chat.checkpointer_dsn or config.database.dsn)
    chat_graph = build_agent_graph(chat_model, registry, config.chat.max_steps, config.chat.max_tool_calls, enable_query_rewrite=config.chat.enable_query_rewrite, checkpointer=checkpointer, max_user_interrupts=config.chat.max_user_interrupts, metrics=metrics, rewrite_model=rewrite_model, controlled_retriever=controlled_retriever)
    chat_server = AgentChatGrpcServer(config.chat.port, ChatStreamService(chat_graph, config.chat.token, config.chat.timeout, mysql, metrics), mysql, config.chat.max_workers)
    opensearch = OpenSearchRepository(config.rag.opensearch) if config.rag.opensearch.enabled else None
    chunker = ParentChildChunker(config.rag.child_size, config.rag.child_overlap, config.rag.parent_size)
    indexer = DocumentIndexer(mysql, vectors, opensearch, logic, downloader, embeddings, ParserRegistry(), chunker, graph_repository=graph_repository, graph_extractor=graph_extractor)
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
        if graph_driver is not None:
            graph_driver.close()
        if opensearch is not None:
            opensearch.close()
        embeddings.close()
        if reranker is not None:
            reranker.close()
        downloader.close()
        logic.close()
        # 主线程退出前关闭异步模型的 HTTP 连接池。
        import asyncio
        asyncio.run(chat_model.aclose())
        if rewrite_model is not None:
            asyncio.run(rewrite_model.aclose())


if __name__ == "__main__":
    main()
