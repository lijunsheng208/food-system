# Graph RAG 对比评估

> 数据集：HowToCook dishes；图候选：阶段 1 离线候选并已导入 Neo4j（user_id=1, knowledge_base_id=1, index_version=1）。
> Graph 查询使用项目 GraphRetriever 连接本地 Neo4j，按 user_id=1、knowledge_base_id=1、index_version=1 实际执行；Milvus 指标引用同一查询集的既有真实 RRF 报告。

## 图数据质量

- 菜谱文件：370
- 图节点：7026
- 图关系：9764
- 图路径有效率：1.0000（关系两端实体均存在）
- Evidence 元数据覆盖率：1.0000（候选实体均带 source_chunk_id；不代表 MySQL 原文已成功回查）

## Graph 查询指标

- Graph 实体关系命中率@1：1.0000（720/720）
- Graph MRR：不适用（当前一跳关系查询未定义候选排序和统一 chunk/document 标签）
- Query 样本数：720
- 图实体名称匹配查询数：720/720
- Neo4j 查询错误数：0
- Graph 查询延迟：平均 8.78 ms，P50 8.79 ms，P95 12.81 ms
- Graph 驱动/查询状态：真实执行

## 关系分布

- CONTAINS_STEP: 3477
- PRECEDES: 3108
- REQUIRES: 3179

## Milvus RRF 基线

Milvus RRF 基线（本次同查询集真实执行）：{"chunk_recall@5": 0.6152777777777778, "chunk_recall@10": 0.7152777777777778, "chunk_recall@20": 0.7902777777777777, "chunk_mrr@10": 0.4403483245149908, "document_recall@10": 0.8444444444444444, "document_mrr@10": 0.6367173721340386, "latency_p50_ms": 1.1803749948740005, "latency_p95_ms": 1.5559579769615084}

## 结论与限制

- 图结构关系有效率可由候选实体 ID 闭包验证，但不等价于语义关系准确率。
- Evidence 可回查率需要连接 MySQL，以 source_chunk_id 实际查询并校验权限/版本。
- 当前 Graph 命中指标是实体关系查询命中率，不等价于 Milvus 的 chunk/document Recall@K 或 MRR；图查询返回未定义统一排名时不能伪造 MRR。
- Milvus 指标来自同一 720 条查询集的既有真实报告；要做严格 Graph Recall@K/MRR，需要将图节点的 source_chunk_id 与 Milvus 标签统一。

