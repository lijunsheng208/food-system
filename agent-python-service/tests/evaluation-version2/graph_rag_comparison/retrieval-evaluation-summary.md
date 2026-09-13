# FamilyOS 菜谱检索评估总结

## 1. 结论摘要

当前菜谱检索评估可以分为四组，不能直接混为同一个实验：

1. 干净原始 query 上的 Dense、Sparse、RRF 和加权融合调参；
2. 人工扰动 query 上的 Query Rewrite 消融；
3. 已知正确菜谱实体后的 Graph Retriever 检索层测试；
4. 真实 LLM 意图识别后的线上端到端路由测试。

当前线上 Vector 已与旧评估的 `hybrid_rrf_k60` 完全对齐：使用原始 query，Dense/Sparse 各召回 50 个候选，通过 Milvus 原生 `hybrid_search + RRFRanker(60)` 返回 TopK。720 条最新端到端测试中，719 条 Vector 的完整 chunk 排名与旧 RRF 逐条一致。

当前主要基线为：

| 指标 | 当前值 |
|---|---:|
| Document Recall@5 | 0.7597 |
| Document Recall@10 | 0.8444 |
| Document Recall@20 | 0.8861 |
| Document MRR@10 | 0.6367 |
| Document NDCG@10 | 0.6865 |
| Chunk Recall@10 | 0.7153 |
| Hard Negative Hit@10 | 0.4153 |
| 约束满足率@10 | 0.4198 |

其中，明确菜名和食材类问题表现较好，口味场景、否定约束和数字约束仍是主要短板。Query Rewrite 对带错别字、口语和方言的噪声 query 有帮助，但没有完全恢复到干净 query 基线。当前通用数据集几乎不触发 Graph，因此不能用于判断 Graph RAG 的端到端增益。

## 2. 数据集概况

| 项目 | 数量或状态 |
|---|---|
| 原始知识来源 | HowToCook 菜谱 Markdown |
| 评估菜谱 | 120 份 |
| 图数据覆盖菜谱 | 370 份 |
| 菜谱类别 | 6 类 |
| 评估 query | 720 条 |
| 每类 query | 120 条 |
| Milvus chunk | 2237 个 |
| Neo4j 节点 | 6978 个 |
| Neo4j 关系 | 9745 条 |
| 标签状态 | `needs_review` |

六个菜谱类别为：

- `aquatic`：水产；
- `breakfast`：早餐；
- `meat_dish`：荤菜；
- `soup`：汤类；
- `staple`：主食；
- `vegetable_dish`：素菜。

每份评估菜谱生成六种 query，因此 120 份菜谱对应 720 条查询。Milvus 和 Neo4j 已使用同一套 canonical `document_id/chunk_id`，可以按相同标签计算指标。

## 3. 指标口径

当前报告沿用旧评估脚本的定义：

- `Document Recall@K`：TopK 中只要出现任一正确文档，就记为 1；
- `Chunk Recall@K`：TopK 中只要出现任一正确 chunk，就记为 1；
- `MRR@10`：第一个正确结果排名的倒数；
- `NDCG@10`：同时考虑多个正样本及其排名位置；
- `Hard Negative Hit@10`：Top10 是否出现预先设置的高相似错误文档，越低越好；
- `约束满足率@10`：Top10 文档满足否定词、时间、温度、用量等约束的比例，越高越好。

这里的 Recall 实际上是 Hit Recall，不是“命中正样本数量 / 全部正样本数量”的严格集合召回率。因为一条 query 通常有 1 至 2 个正样本 chunk，后续若需要评价完整证据覆盖，应额外计算严格 Recall，不能替换或混用当前口径。

## 4. Query 类型

| 类型 | 数量 | 示例意图 | 主要检索难点 | 当前适合路径 |
|---|---:|---|---|---|
| `dish_name` | 120 | 查询指定菜谱的用料和步骤 | 菜名别名、错别字 | Sparse/Hybrid |
| `ingredient` | 120 | 根据已有食材寻找菜谱 | 多菜共享相同食材 | Dense + Sparse |
| `taste_scene` | 120 | 根据口味和场景找菜 | “清淡、下饭”等词区分度低 | Dense/重排 |
| `semantic_description` | 120 | 根据步骤描述反查菜谱 | 多菜步骤高度相似 | Dense + 重排 |
| `negative` | 120 | 不含某食材或不用某方法 | 向量相似度不理解排除条件 | 结构化过滤 + 重排 |
| `numeric` | 120 | 时间、温度、克数、热量约束 | 向量检索不擅长精确比较 | 结构化过滤 + 重排 |

这些 query 的主要目标是找到正确菜谱或原文 chunk，而不是多跳关系推理。因此，它们天然更偏 Vector Retrieval，并不是合适的 Graph 路由准确率测试集。

## 5. 干净 Query 的检索方法对比

以下实验均使用原始干净 query、相同 Milvus Collection 和相同 720 条标签。

| 方法 | Doc R@10 | Doc MRR@10 | Doc NDCG@10 | Chunk R@10 | HardNeg Hit@10 | 约束满足@10 |
|---|---:|---:|---:|---:|---:|---:|
| Dense | 0.7875 | 0.5972 | 0.6432 | 0.6625 | 0.3986 | 0.4483 |
| Sparse | 0.8222 | 0.5929 | 0.6479 | 0.6542 | 0.4125 | 0.3993 |
| RRF k10 | 0.8417 | 0.6412 | 0.6895 | 0.7181 | 0.4056 | 0.4209 |
| RRF k20 | **0.8486** | 0.6393 | 0.6894 | 0.7194 | 0.4194 | 0.4202 |
| RRF k60 | 0.8444 | 0.6367 | 0.6865 | 0.7153 | 0.4153 | 0.4198 |
| RRF k100 | 0.8458 | 0.6358 | 0.6861 | 0.7139 | 0.4139 | 0.4200 |
| Weighted 0.3/0.7 | 0.8417 | 0.6314 | 0.6820 | 0.7111 | 0.4264 | 0.4160 |
| Weighted 0.5/0.5 | 0.8375 | **0.6451** | **0.6913** | **0.7264** | 0.4153 | 0.4236 |
| Weighted 0.7/0.3 | 0.8403 | 0.6399 | 0.6879 | 0.7222 | 0.4167 | 0.4281 |

结论：

- 以 Document Recall@10 为首要目标时，`RRF k20` 最好，比当前 k60 高 0.0042；
- 以 Chunk Recall、MRR 和 NDCG 为首要目标时，`Weighted 0.5/0.5` 最好；
- 单纯调 RRF 常数或 Dense/Sparse 权重，提升幅度约为 0.4 至 1.1 个百分点，无法解决数字和否定约束问题；
- Dense 的总体约束满足率最高，但整体 Recall 低于混合检索，说明约束指标与召回指标存在权衡；
- 当前线上使用 `RRF k60` 是稳定基线，不是本实验中每项指标的最优参数。

## 6. 当前基线的分类型表现

以下为干净 query 上 `hybrid_rrf_k60` 的结果：

| Query 类型 | Doc R@10 | Doc MRR@10 | Doc NDCG@10 | Chunk R@10 | 约束满足@10 |
|---|---:|---:|---:|---:|---:|
| `dish_name` | **0.9917** | **0.9833** | **0.9855** | **0.9167** | - |
| `ingredient` | 0.9167 | 0.7823 | 0.8156 | 0.8167 | - |
| `numeric` | 0.8333 | 0.5410 | 0.6105 | 0.6833 | **0.2960** |
| `taste_scene` | 0.7917 | 0.5289 | 0.5913 | **0.5417** | - |
| `semantic_description` | 0.7750 | 0.5195 | 0.5815 | 0.6833 | - |
| `negative` | **0.7583** | **0.4653** | **0.5346** | 0.6500 | 0.5437 |

分类型结论：

- `dish_name` 已接近饱和，继续调融合参数的收益有限；
- `ingredient` 总体可用，但共享食材会产生较多相似菜谱；
- `taste_scene` 的 Chunk Recall 最低，说明口味词能找到相关菜谱，却不容易定位标签指定的证据块；
- `negative` 的 Doc Recall 和 MRR 最低，原因是“包含姜”和“不含姜”在向量空间中仍高度相似；
- `numeric` 的约束满足率只有 0.2960，是当前最明确的结构化检索缺口；
- `semantic_description` 容易召回烹饪动作相似、但实际菜谱不同的 Hard Negative。

## 7. Query Rewrite 消融

Rewrite 实验不是对干净 query 再做改写，而是先生成包含错别字、方言、口语、省略和表达扰动的 noisy query，再比较是否经过 Qwen Rewrite。

本次 720 条 noisy query 的 Qwen Rewrite 状态均为 `success`，没有 fallback。

| 数据与方法 | Doc R@10 | Doc MRR@10 | Chunk R@10 | 约束满足@10 |
|---|---:|---:|---:|---:|
| 干净 query，RRF k60 | **0.8444** | **0.6367** | **0.7153** | 0.4198 |
| Noisy query，不 Rewrite | 0.8222 | 0.6102 | 0.6972 | 0.4200 |
| Noisy query，Qwen Rewrite | 0.8347 | 0.6237 | 0.6986 | **0.4275** |

Rewrite 相对 Noisy 不改写的变化：

| 指标 | 变化 |
|---|---:|
| Document Recall@10 | +0.0125 |
| Document MRR@10 | +0.0135 |
| Chunk Recall@10 | +0.0014 |
| 约束满足率@10 | +0.0075 |

结论：

- Rewrite 对文档定位和首个正确结果排名有稳定帮助；
- Rewrite 对 Chunk Recall 帮助很小，说明文本规范化不能解决父子块定位问题；
- Rewrite 后仍低于干净 query：Doc Recall@10 低 0.0097，Chunk Recall@10 低 0.0167；
- Rewrite 更适合用于错别字、方言、口语和上下文省略，不应默认改写所有独立、干净的 Vector query；
- Rewrite 必须保留否定词、数字、单位、食材和过敏原，否则可能提高语义相似度却破坏业务约束。

## 8. Graph Retriever 与端到端路由

### 8.1 Graph 检索层测试

在直接向 Graph Retriever 提供正确菜谱实体名称时：

| 指标 | Graph Retriever | Milvus RRF k60 |
|---|---:|---:|
| Chunk Recall@10 | 0.8812 | 0.7153 |
| Chunk MRR@10 | 0.7878 | 0.4403 |
| Document Recall@10 | 1.0000 | 0.8444 |
| Document MRR@10 | 0.9958 | 0.6367 |

该结果证明 Neo4j 中的菜谱关系可以回查到正确 canonical chunk，但它不是自然语言端到端结果。测试过程从标签对应的菜谱中直接取得正确 Recipe 实体，相当于提前知道图查询起点，不能据此宣称 Graph RAG 已在真实用户问题上优于 Vector。

### 8.2 最新端到端测试

当前真实流程为：

```text
原始问题
  -> Qwen 意图识别
  -> RetrievalPlan
  -> Vector / Graph / Hybrid
  -> canonical chunk_id 去重
```

最新 720 条执行结果：

| 路由 | 数量 | Chunk R@10 | Chunk MRR@10 | Doc R@10 | Doc MRR@10 |
|---|---:|---:|---:|---:|---:|
| Vector | 719 | 0.7149 | 0.4408 | 0.8442 | 0.6362 |
| Hybrid | 1 | 1.0000 | 0.1667 | 1.0000 | 1.0000 |
| Graph | 0 | - | - | - | - |

总体指标与旧 `hybrid_rrf_k60` 在四位小数下完全一致，719 条 Vector 的完整 chunk 排名也与旧基线逐条一致。这说明线上 Vector 实现已经正确对齐，但当前数据集不能体现 Graph 的收益：99.86% 的查询都被路由到 Vector，且数据集中没有 `expected_route`，无法计算路由 Accuracy 或 F1。

端到端 P50 为 1212.39 ms，P95 为 2063.45 ms；旧 Milvus 报告的 P95 约为 1.56 ms。两者不属于相同延迟口径：前者包含真实 LLM 意图识别和逐条 Query Embedding，后者只统计预编码后的 Milvus 查询。

## 9. 当前可确认的结论

1. 线上 Vector 已与旧 RRF k60 基线对齐，当前流程没有因为接入路由而降低 Vector 排名质量。
2. RRF k20 的 Document Recall 略高，Weighted 0.5/0.5 的 Chunk Recall、MRR 和 NDCG 略高，但单纯调参收益有限。
3. Query Rewrite 能缓解噪声 query，对干净独立 query 不应强制启用。
4. 当前 Recall 的主要损失集中在口味场景、否定和数字约束，而不是明确菜名查询。
5. Document Recall 高于 Chunk Recall，说明系统经常找对菜谱但没有返回最合适的证据块。
6. Graph Retriever 在已知正确起点时表现较高，但当前通用数据集几乎不触发 Graph，尚未验证自然语言端到端 Graph 增益。
7. 标签状态仍为 `needs_review`，在进行模型选择或论文结论前需要人工抽样审核。

## 10. 后续评估建议

建议按以下顺序推进：

1. 人工审核 `needs_review` 标签，确认正样本 chunk、Hard Negative 和约束字段；
2. 固定当前 `RRF k60` 为可复现基线，同时保留 `RRF k20` 和 `Weighted 0.5/0.5` 作为候选；
3. 增加“标题/章节增强后的 child embedding”和“命中 child 后 sibling 回查”的消融实验；
4. 在 RRF Top50 候选上加入 Cross-Encoder，重点观察 MRR、NDCG 和 Hard Negative Hit；
5. 对数字、时间、温度、用量和否定条件增加结构化过滤实验；
6. 单独建立 Graph/Hybrid 测试集，标注 `expected_route`、实体、关系、路径和证据 chunk；
7. 分别报告检索耗时、LLM 路由耗时和完整端到端耗时，避免混用延迟口径。

## 11. 结果来源

- 干净 query 调参：`tests/evaluation-version1/experiments/sparse-dense-all/sparse-dense-all.md`
- Noisy 不 Rewrite：`tests/evaluation-version1/experiments/sparse-dense-all/noisy_no_rewrite.md`
- Noisy + Rewrite：`tests/evaluation-version1/experiments/sparse-dense-all/noisy_with_rewrite.md`
- 最新端到端结果：`tests/evaluation-version2/graph_rag_comparison/end_to_end_report.md`
- 端到端逐 query 明细：`tests/evaluation-version2/graph_rag_comparison/end_to_end_results.jsonl`
- Graph 检索层对比：`tests/evaluation-version2/graph_rag_comparison/report.md`
