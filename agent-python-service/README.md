# FamilyOS Python Agent Indexer

该服务替换 Go `agent-service` 的文档索引 Worker，外部契约保持不变：

- RocketMQ Topic `familyos-rag-document`，Tag `INDEX`
- JSON 事件类型 `document.index.requested`，字段与 Go `DocumentIndexReceiver` 一致
- Logic `KnowledgeInternalService` 的三个 gRPC RPC
- Agent MySQL `agent_document_index_task`、`agent_document_chunk`
- PostgreSQL `agent_document_vectors` 和可选 OpenSearch BM25

## 解析和索引流程

```text
下载票据 → Unstructured 解析 MD/DOC/DOCX/PDF 元素树
        → 按元素 parent_id 聚合父块
        → RecursiveCharacterTextSplitter 细分重叠子块
        → 子块 Embedding + pgvector
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
