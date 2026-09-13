# LLM 意图识别 + 受控路由端到端评估

- 查询数：720
- LLM：真实调用当前 graph_extraction 配置模型
- Vector：原始 query + Milvus 原生 hybrid_search + RRFRanker(60) + 每路 50 候选
- Neo4j 命名空间：900001/900001/1
- Milvus Collection：`familyos_document_chunks_eval_v1`
- 错误数：0
- Vector 完整排名与旧 RRF 逐条一致：719/719

## 总体对比

| 指标 | 旧 Milvus RRF | 当前完整流程 | 变化 |
|---|---:|---:|---:|
| Chunk Recall@5 | 0.6153 | 0.6153 | +0.0000 |
| Chunk Recall@10 | 0.7153 | 0.7153 | +0.0000 |
| Chunk Recall@20 | 0.7903 | 0.7903 | +0.0000 |
| Chunk MRR@10 | 0.4403 | 0.4404 | +0.0000 |
| Document Recall@5 | 0.7597 | 0.7597 | +0.0000 |
| Document Recall@10 | 0.8444 | 0.8444 | +0.0000 |
| Document Recall@20 | 0.8861 | 0.8861 | +0.0000 |
| Document MRR@10 | 0.6367 | 0.6367 | +0.0000 |

## 路由分布与指标

| 路由 | 数量 | Chunk R@10 | Chunk MRR@10 | Document R@10 | Document MRR@10 |
|---|---:|---:|---:|---:|---:|
| hybrid | 1 | 1.0000 | 0.1667 | 1.0000 | 1.0000 |
| vector | 719 | 0.7149 | 0.4408 | 0.8442 | 0.6362 |

## 延迟

- 当前完整流程 P50：1212.39 ms
- 当前完整流程 P95：2063.45 ms
- 旧评估 Milvus P95：1.56 ms
- 当前延迟包含逐条真实 LLM 意图识别和查询 Embedding；旧延迟只统计预编码后的 Milvus 查询，两者不属于同一耗时口径。

## 说明

- Recall 使用旧评估定义：Top-K 中至少出现一个正样本即记为 1。
- 当前标签没有 expected_route，因此无法计算路由准确率。
- 逐查询预测、计划、结果 ID 和耗时保存在 end_to_end_results.jsonl。
