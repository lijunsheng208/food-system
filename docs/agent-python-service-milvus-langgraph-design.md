# FamilyOS Python Agent 服务开发阶段设计（评估稿）

> 状态：开发前评估稿  
> 目标：使用 Python + Milvus + LangGraph，逐步替换 Go `agent-service`。  
> 参考：`all-in-rag` 的 LangGraph Agentic RAG、Milvus Hybrid Search 和模块化 RAG 实践。

## 1. 目标与非目标

### 1.1 目标

- 用 Python 服务同时承载文档索引 Worker 和 Agent Chat Server。
- 用 Milvus 保存文档 Chunk 的 Dense/Sparse 向量，并首期采用 Milvus 原生 Hybrid Search。
- 用 LangGraph 编排查询改写、检索、业务 Tool、回答和失败重试。
- 保持现有 RocketMQ、Logic gRPC、Chat gRPC 和 MySQL 业务契约兼容；新增能力通过适配层接入。
- 保留文档父子块、索引版本和权限过滤语义。

### 1.2 首期非目标

- 不引入图数据库或 Graph RAG。
- 不在首期迁移家庭业务数据存储。
- 不直接复制 `all-in-rag` 的教学代码到生产路径。
- 不以更换数据库为理由修改无关的上传、OSS 和 Logic 服务。

## 2. 现状与迁移边界

当前 Go `agent-service` 有两个逻辑模块：

1. Indexer Worker：下载、解析、切片、Embedding、pgvector 和 OpenSearch 写入。
2. Agent Chat Server：Query Rewrite、混合检索、业务 Tool、Eino ReAct 和 gRPC 流式回答。

当前 `agent-python-service` 只实现了第一模块，并且向量写入仍使用 PostgreSQL pgvector。本项目要把第一模块改为 Milvus，并补齐第二模块。

文件上传仍属于 Logic/Knowledge 服务和 OSS 流程；Python Agent 只通过内部 RPC 获取下载票据。

## 3. 目标技术架构

```text
客户端上传 → Logic/OSS → document.index.requested
                              ↓ RocketMQ
                    Python Indexer Worker
                    ├── Unstructured 解析
                    ├── 父子 Chunk
                    ├── Dense/Sparse Embedding
                    └── Milvus 写入

客户端 Chat → Python gRPC Chat Server → LangGraph
                                         ├── Query Rewrite
                                         ├── Milvus Hybrid Retrieval
                                         ├── FamilyOS Business Tools
                                         ├── Context Grading / Retry
                                         └── Answer Streaming
```

职责分层：

```text
transport：gRPC、RocketMQ 协议解析
service：任务状态、索引编排、错误映射
repository：MySQL、Milvus 持久化
retrieval：Dense、Sparse、Hybrid、Rerank
agent：LangGraph StateGraph 和节点
clients：Logic、Embedding、模型和外部服务
```

## 4. Milvus 数据设计

首期确定创建 `familyos_document_chunks_v1` Collection，并同时写入 Dense 和 Sparse 向量；不把 OpenSearch 作为首期检索依赖。

### 4.1 字段

```text
chunk_id             VarChar primary key
document_id          Int64
knowledge_base_id    Int64
user_id              Int64
index_version        Int64
chunk_index          Int32
parent_id            VarChar
content_sha256       VarChar
content              VarChar
metadata             JSON
active               Bool
dense_vector         FloatVector
sparse_vector        SparseFloatVector
```

Dense 使用 COSINE；索引优先评估 HNSW 或 AUTOINDEX。向量维度必须与 Embedding 模型配置严格一致。`content` 在 Milvus 中冗余保存，用于直接组装检索上下文，避免每个候选 Chunk 再回 MySQL 查询；MySQL 仍是内容、权限和父子结构的权威数据源，Milvus 中的内容是检索读副本。

### 4.2 一致性和版本

Milvus 与 MySQL 没有跨库事务，不能依赖单次事务保证一致性。索引一次文档版本时应：

1. 先生成并校验全部 Chunk 和向量。
2. 以 `document_id + index_version + chunk_index` 做幂等写入。
3. 校验 Milvus 写入数量、维度和哈希。
4. 写入/更新活动版本状态。
5. 成功后才回调 Logic `CompleteDocumentIndex`。
6. 失败时删除未完成版本，并保留可重试任务。

建议活动版本以 MySQL/Logic 为权威，Milvus 查询使用明确的 `index_version` 过滤，而不是只依赖最终一致的 `active` 字段。

## 5. Dense、Sparse 与 Hybrid 检索

首期采用 Milvus Dense + Sparse Hybrid Search，使用 Weighted RRF 或 Milvus RRF 融合。

- Dense：处理同义表达、口语化问题和语义相似内容。
- Sparse：处理人名、菜名、过敏原、日期、数字和专有名词。
- Reranker：作为可选第二阶段组件，不阻塞首期上线。

Sparse Encoder 必须通过中文业务数据集评估。`all-in-rag` 中的 TF-IDF 示例可用于验证流程，但不能直接视为生产级 Sparse 模型。

首期不保留 OpenSearch 作为检索路径。若 Milvus Sparse 的中文召回未达指标，优先调整 Sparse Encoder、文本预处理和融合参数；只有评估证明无法满足业务指标时，才单独发起引入 OpenSearch 的变更评审。

## 6. LangGraph Agent 设计

不要把完整业务流程隐藏在黑盒 AgentExecutor 中，首期使用显式 `StateGraph`，并加入有上限、可观测、可中断的受控自主循环：

```text
START
  → load_conversation
  → rewrite_query
  → classify_intent
      ├── casual_chat → generate_answer
      ├── knowledge_search → hybrid_retrieve
      ├── family_tool → call_family_tools
      └── dish_tool → call_dish_tools
  → grade_context
      ├── sufficient → generate_answer
      └── insufficient → retry_rewrite（最多 N 次）
  → validate_answer
  → END
```

Graph State 至少包含：

```text
messages、original_query、rewritten_query、intent、documents、tool_results、retry_count、answer
```

自主循环只允许在检索改写、检索重试和 Tool 选择范围内运行，不允许模型无限创建步骤或绕过权限。必须配置最大循环次数、总超时、单节点超时、Tool 白名单和失败终态，以满足企业系统对延迟、成本和可审计性的要求。

业务 Tool 必须复用现有 Logic 服务和权限边界，当前用户身份来自已验证的 Access Token，不接受客户端提交的 `user_id` 作为操作者身份。

## 7. 开发阶段与验收标准

### 阶段 A：基础设施和接口抽象

- [ ] 引入 `pymilvus`、`langgraph`、LangChain Core 相关依赖。
- [ ] 抽象 `VectorRepository` 和 `HybridRetriever` 接口。
- [ ] 保留现有 MySQL 父子 Chunk、任务状态和 RocketMQ 契约。
- [ ] 完成 Milvus 本地开发环境和健康检查。
- [ ] 固化 gRPC、RocketMQ、Logic 的现有消息和 RPC 契约。

验收：服务可启动；Collection 可幂等创建；配置缺失时明确失败。

### 阶段 B：Milvus Indexer

- [ ] 实现批量插入、幂等替换、版本切换和失败删除。
- [ ] 将现有 pgvector 写入替换为 Milvus 写入。
- [ ] 对空文档、维度不匹配、重复消息和超时增加回归测试。

验收：同一索引事件重复消费不会产生重复 Chunk；成功版本可检索；失败版本不会被查询到。

### 阶段 C：Milvus Hybrid Retrieval

- [ ] 实现 Dense Search、Sparse Search 和 Hybrid Search。
- [ ] 实现知识库、文档和活动版本过滤。
- [ ] 对 Dense、Sparse、Hybrid 三种检索进行离线评估，并验证 Milvus 原生融合参数。

验收：中文关键词、同义问法、否定词和数字查询均有离线评测结果。

### 阶段 D：LangGraph Chat Server

- [ ] 实现 Query Rewrite 节点。
- [ ] 实现知识库检索节点和业务 Tool 节点。
- [ ] 实现上下文不足重试、最大步数和错误映射。
- [ ] 复用现有 Chat gRPC 流式协议。

验收：普通聊天、知识库问答、业务 Tool、检索失败和模型超时均有测试覆盖。

### 阶段 E：灰度和下线 Go

- [ ] Indexer 双写或按知识库灰度。
- [ ] Chat Server 按租户/知识库灰度读取。
- [ ] 监控错误率、P95 延迟、召回率和 Token 成本。
- [ ] 保留 pgvector 回滚窗口后再移除旧代码。

## 8. 评估指标

### 检索质量

- Recall@K
- MRR/NDCG
- Dense、Sparse、Hybrid 的 TopK 对比
- 关键词、同义表达、数字、否定和中文专名专项集

### 系统指标

- 索引成功率
- 重复消费幂等率
- Milvus 插入 P95
- 检索 P50/P95/P99
- Chat 首 token 延迟和完整响应延迟
- 失败重试后的最终成功率

### 资源和成本

- Milvus 内存、磁盘和索引构建耗时
- Embedding 调用量和费用
- Chat 模型调用量和费用
- OpenSearch 是否仍有必要保留

## 9. 主要风险与决策点

1. Milvus Sparse 的中文效果需要通过业务数据集验证；首期不引入 OpenSearch，未达标时再发起单独变更评审。
2. Milvus 没有跨 MySQL 事务，必须通过版本状态、幂等和补偿保证一致性。
3. `all-in-rag` 示例偏教学用途，生产代码需要补充权限、重试、监控和数据隔离。
4. Embedding 模型或维度变化时新建 `v2` Collection，不原地修改旧 Collection。
5. LangGraph 图状态应保持可序列化，便于调试、重试和后续持久化。

## 10. 首期建议结论

首期目标确定为：

```text
Python Indexer Worker
    + Milvus Dense/Sparse Hybrid Search
    + MySQL Chunk 和任务状态

Python LangGraph Chat Server
    + Milvus Hybrid Retrieval
    + FamilyOS 业务 Tools
    + 现有 gRPC/RocketMQ/Logic 契约
```

首期明确不引入 OpenSearch 检索路径。内容存储采用“双层职责”：MySQL 保存权威父子 Chunk 和权限数据，Milvus 保存检索所需的 `content` 冗余副本及向量；检索阶段直接使用 Milvus 内容降低延迟，回答落地前可按 `chunk_id` 回 MySQL 做权限和版本复核。



# 错误解决方法

