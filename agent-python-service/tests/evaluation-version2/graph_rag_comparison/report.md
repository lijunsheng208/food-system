# Graph RAG 对比评估

> 数据集：HowToCook dishes；Neo4j 使用隔离评估命名空间（user_id=900001、knowledge_base_id=900001、index_version=1），图来源 ID 已重写为 Milvus canonical document/chunk ID。
> Graph 与 Milvus 使用同一份 720 条 query、positive_chunks 和 positive_documents。

## 图数据质量

- 菜谱文件：370
- 图节点：6978
- 图关系：9745
- 图路径有效率：1.0000（导入时已校验关系两端实体存在）

## Graph 查询指标

- 实体关系命中率@1：1.0000（720/720）
- Chunk Recall@5/10/20：0.8812 / 0.8812 / 0.8812
- Document Recall@5/10/20：1.0000 / 1.0000 / 1.0000
- Chunk MRR@10：0.7878
- Document MRR@10：0.9958
- 查询数：720；实体名称匹配：720/720；查询错误：0
- 查询延迟：平均 11.44 ms，P50 11.83 ms，P95 15.89 ms
- Graph 驱动状态：真实执行

## Milvus RRF 基线

Milvus RRF 基线（本次同查询集真实执行）：{"chunk_recall@5": 0.6152777777777778, "chunk_recall@10": 0.7152777777777778, "chunk_recall@20": 0.7902777777777777, "chunk_mrr@10": 0.4403483245149908, "document_recall@10": 0.8444444444444444, "document_mrr@10": 0.6367173721340386, "latency_p50_ms": 1.1803749948740005, "latency_p95_ms": 1.5559579769615084}

## 结论与限制

- Graph 与 Milvus 按 canonical source_chunk_id/document_id 使用同一套标签计算。
- 当前 Graph 排名使用 Neo4j 一跳查询返回顺序，尚未加入路径相关性排序。
- LLM 意图识别和 traditional/graph/combined 路由准确率需要额外 expected_route 标注。
