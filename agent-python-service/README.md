# FamilyOS Python Agent Service

## 目录结构

服务按设计稿中的职责边界组织。当前索引 Worker 的平铺模块暂时保留，后续阶段在修改相应功能时逐步迁入目标包，避免目录调整同时改变线上行为。

```text
agent-python-service/
├── migrations/                    # MySQL 等持久化迁移
├── scripts/                       # 运维脚本
├── src/familyos_agent/
│   ├── agent/                     # LangGraph StateGraph
│   │   ├── nodes/                 # 改写、分类、检索、生成和校验节点
│   │   └── tools/                 # FamilyOS 业务 Tool 适配器
│   ├── clients/                   # Logic、Embedding、模型和外部客户端
│   ├── domain/                    # 领域模型、值对象和业务错误
│   ├── generated/                 # Proto 自动生成代码
│   ├── repositories/              # MySQL、Milvus 持久化接口与实现
│   ├── retrieval/                 # Dense、Sparse、Hybrid 和 Rerank
│   ├── services/                  # 索引、Chat 和任务状态编排
│   ├── transport/
│   │   ├── grpc/                  # Chat gRPC 入站协议
│   │   └── rocketmq/              # 索引事件消费与解析
│   ├── workers/                   # 索引任务执行、重试和补偿
│   ├── config.py                  # 应用配置（后续可迁入 core）
│   ├── main.py                    # 进程组装和生命周期入口
│   └── ...                        # 迁移前的现有索引模块
└── tests/
    ├── unit/                      # 无外部服务的单元测试
    ├── integration/               # MySQL、Milvus、gRPC 和 MQ 集成测试
    └── evaluation/                # Dense/Sparse/Hybrid 离线评测
```

依赖方向保持为 `transport/workers -> services -> domain`。`repositories`、`retrieval` 和 `clients` 实现由入口注入应用服务；`agent` 通过应用接口使用检索和业务 Tool，不直接解析 gRPC 或 RocketMQ 协议。`generated` 只由 Proto 生成流程维护。

现有模块的计划归属如下：

| 现有模块 | 目标目录 |
| --- | --- |
| `messaging.py` | `transport/rocketmq/` |
| `indexing.py` | `services/` 与 `workers/` |
| `repositories.py` | 已迁入 `repositories/implementations.py` |
| `clients.py` | 已迁入 `clients/implementations.py` |
| `domain.py` | 已迁入 `domain/models.py` |
| `parsing.py`、`chunking.py` | `services/` |

`agent`、`retrieval` 和 `transport/grpc` 将分别在 LangGraph、Milvus Hybrid Retrieval 和 Chat Server 阶段补充实现。包骨架不提供空的业务类，避免尚未成立的接口被其他模块依赖。

## 阶段 A 基础设施

阶段 A 已加入 `VectorRepository`、`HybridRetriever` 接口和 Milvus Collection 初始化。服务启动时会先检查 Milvus 连接，然后幂等创建或校验 `familyos_document_chunks_v1`；字段缺失或 Dense 向量维度不一致时直接终止启动。

本地启动基础设施：

```bash
docker compose -f docker-compose.infrastructure.yml up -d milvus-etcd milvus-minio milvus
curl --fail http://127.0.0.1:9091/healthz
```

开发配置从示例复制后通过环境变量注入真实密钥：

```bash
cd agent-python-service
cp config/config.yaml.example config/config.yaml
python -m familyos_agent --config config/config.yaml
```

阶段 B 已将 Indexer 切换为本地 BGE-M3 + Milvus：BGE-M3 同时生成 1024 维 Dense 和 lexical Sparse 向量，Milvus 按文档版本删除后批量插入，重复事件不会累积 Chunk。失败补偿会删除当前版本；Hybrid Search 和活动版本过滤属于阶段 C。模型目录默认为 `models/bge-m3`，该目录已加入 `.gitignore`。

该服务替换 Go `agent-service` 的文档索引 Worker，外部契约保持不变：

- RocketMQ Topic `familyos-rag-document`，Tag `INDEX`
- JSON 事件类型 `document.index.requested`，字段与 Go `DocumentIndexReceiver` 一致
- Logic `KnowledgeInternalService` 的三个 gRPC RPC
- Agent MySQL `agent_document_index_task`、`agent_document_chunk`
- Milvus `familyos_document_chunks_v1`（Dense/Sparse）和可选 OpenSearch BM25

## 解析和索引流程

```text
下载票据 → Unstructured 解析 MD/DOC/DOCX/PDF 元素树
        → 按元素 parent_id 聚合父块
        → RecursiveCharacterTextSplitter 细分重叠子块
        → 子块 BGE-M3 Dense/Sparse + Milvus
        → 子块 OpenSearch BM25
```

父块和子块都保存到 MySQL，子块通过 `parent_id` 指向父块；父块不写入向量和 BM25。父块元数据保留 Unstructured 的原始 `parent_id` 和元素 ID，子块继承这些结构信息。PDF 的 OCR 和版面解析能力由 Unstructured 的 `auto` 策略及其 PDF 依赖提供。

## 启动

使用 Python 3.10 或更高版本安装依赖并执行仓库迁移（生成的 gRPC 代码要求 protobuf 7）：

```bash
cd agent-python-service
python -m pip install -e .
python -m nltk.downloader punkt_tab averaged_perceptron_tagger_eng
mysql < migrations/001_parent_child_chunks.sql
python -m familyos_agent --config config/config.yaml
```

Unstructured 的文本类型识别依赖上述 NLTK 数据；离线部署时应在镜像构建阶段预置。DOC 解析还要求系统安装 LibreOffice，PDF 的 `hi_res`/OCR 能力需要 `unstructured[pdf]` 引入的模型依赖及对应系统库。

配置可沿用 Go 的 `FAMILYOS_AGENT_*` 环境变量。切换期间只运行一个服务使用同一个 RocketMQ consumer group；若 Go 和 Python 同时运行，请为灰度实例配置不同 group，避免消息被两边负载均衡分走。
