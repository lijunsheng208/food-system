# 当前检索流程与 Milvus RRF 对比评估

> 历史结果：本报告生成于线上检索器切换到 Milvus 原生 `hybrid_search + RRFRanker` 之前。2026-09-13 已完成对齐，报告中的“当前完整流程”指标需要重新执行后才能代表最新代码。

## 评估范围

- 查询集：`evaluation/datasets/labels/queries.jsonl`
- 查询数：720
- 正样本标签：相同的 `positive_chunks` 和 `positive_documents`
- 旧方案：原始 query 直接调用 Milvus Dense/Sparse RRF，取 `hybrid_rrf_k60`
- 当前方案：真实 Qwen 意图识别并生成 `RetrievalPlan`，再由正式 `ControlledRetriever` 执行 Vector、Graph 或 Hybrid 检索
- 图数据：Neo4j 隔离命名空间 `900001/900001/1`
- 向量数据：Milvus Collection `familyos_document_chunks_eval_v1`

## 总体结果

| 指标 | 旧 Milvus RRF | 当前完整流程 | 变化 |
|---|---:|---:|---:|
| Chunk Recall@5 | 0.6153 | 0.4486 | -0.1667 |
| Chunk Recall@10 | 0.7153 | 0.5549 | -0.1604 |
| Chunk Recall@20 | 0.7903 | 0.6431 | -0.1472 |
| Chunk MRR@10 | 0.4403 | 0.4426 | +0.0022 |
| Document Recall@5 | 0.7597 | 0.7778 | +0.0181 |
| Document Recall@10 | 0.8444 | 0.8583 | +0.0139 |
| Document Recall@20 | 0.8861 | 0.8806 | -0.0056 |
| Document MRR@10 | 0.6367 | 0.6371 | +0.0004 |
| P50 延迟 | 1.18 ms | 1256.21 ms | +1255.03 ms |
| P95 延迟 | 1.56 ms | 2241.29 ms | +2239.73 ms |

## 当前路由分布

| 路由 | 查询数 | 占比 | Chunk R@10 | Chunk MRR@10 | Document R@10 | Document MRR@10 |
|---|---:|---:|---:|---:|---:|---:|
| vector | 718 | 99.72% | 0.5543 | 0.4422 | 0.8579 | 0.6361 |
| hybrid | 2 | 0.28% | 0.7500 | 0.5833 | 1.0000 | 1.0000 |
| graph | 0 | 0.00% | - | - | - | - |

两条 Hybrid 查询分别以“利提巧卡”和“微波葱姜黑鳕鱼”为图查询起点。全部 720 条调用均成功，没有检索错误。

## 按查询类型对比

| Query Type | 当前 Chunk R@10 | 旧 RRF Chunk R@10 | 当前 Doc R@10 | 旧 RRF Doc R@10 |
|---|---:|---:|---:|---:|
| dish_name | 0.8000 | 0.9167 | 1.0000 | 0.9917 |
| ingredient | 0.6917 | 0.8167 | 0.9500 | 0.9167 |
| taste_scene | 0.4083 | 0.5417 | 0.8083 | 0.7917 |
| semantic_description | 0.4625 | 0.6833 | 0.8167 | 0.7750 |
| negative | 0.4458 | 0.6500 | 0.7750 | 0.7583 |
| numeric | 0.5208 | 0.6833 | 0.8000 | 0.8333 |

## 结论

当前完整流程没有在这套数据上证明 Graph RAG 带来了整体提升。文档级 Recall@10 从 0.8444 小幅提高到 0.8583，但 Chunk Recall@10 从 0.7153 降到 0.5549。说明 LLM 改写仍能找到正确菜谱，却更难命中标签指定的正确子块。

更关键的是，当前路由器将 99.72% 的问题判为 Vector，纯 Graph 为 0。因此这次结果主要衡量“LLM 查询改写 + Milvus RRF”，不能用来宣称 Graph 检索优于原方案。此前 Graph Retriever 单独取得的 Chunk Recall@10=0.8812，是已知菜谱实体名称作为图查询起点的检索层上限，不是自然语言意图识别后的端到端效果。

当前查询集主要面向文档定位，缺少明确标注的关系、多跳和子图问题，也没有 `expected_route`。下一步需要增加 Graph/Hybrid 路由测试集并人工标注期望路由，才能计算路由 Accuracy/F1，并判断 LLM 是否正确选择了 Graph。

## 结果文件

- 当前完整流程：`end_to_end_report.md`
- 当前逐查询明细：`end_to_end_results.jsonl`
- 旧 Milvus RRF：`milvus_retrieval_eval.md`
- Graph Retriever 单独评估：`report.md`
