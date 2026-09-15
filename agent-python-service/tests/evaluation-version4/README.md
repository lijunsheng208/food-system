# 菜谱纯检索评测 V4

V4 只评估检索链路，不调用 LangGraph Agent、聊天模型或答案生成模型：

```text
Query
  -> Dense / Sparse / RRF Child 初召回
  -> Parent 激活与同 Parent Child 扩展
  -> 可选 Cross-Encoder 重排
  -> 最终 Child Top-K
```

它回答三个问题：初召回是否找到正确文档、是否激活全部必要 Parent、最终 Top-K 是否包含完整证据。

## 数据集

权威 Query 文件为 `datasets/queries.jsonl`，严格 Child Chunk qrels 为 `datasets/chunk_gold.jsonl`，二者都由 V1 的全量 370 篇菜谱 Chunk 映射生成。固定配额如下：

| query_type | 数量 | Gold |
|---|---:|---|
| `dish_lookup` | 30 | 正确 Document |
| `ingredient_fact` | 45 | 原料 Parent |
| `calculation_fact` | 45 | 计算 Parent/Child |
| `procedure_fact` | 45 | 操作 Parent/Child |
| `cross_parent` | 60 | 两个以上 Parent |
| `recommendation` | 45 | 完整相关 Document 集合 |
| `constraint` | 20 | 满足全部约束的 Document 集合 |
| `unanswerable` | 10 | 无正例 |

`evidence_groups[].acceptable_child_ids` 表示等价证据，命中任意一个即可覆盖该证据组。`acceptable_parent_ids` 使用相同语义。跨 Parent Query 通过多个必需证据组表达，而不是把正例压成一个扁平 Chunk 列表。

`chunk_gold.jsonl` 只覆盖拥有明确 Child 证据的 195 条事实型 Query，共包含 260 条逐 Chunk relevance judgment。每条记录使用 `query_id` 关联 Query，并平铺 `relevant_child_ids` 和带 Document/Parent/Source 归属的 `judgments`。指定菜名、推荐、约束和无答案 Query 没有稳定的 Child 级必要证据，因此不参与 Chunk Recall 的分母。

严格 `ChunkRecall@K` 按 Child ID 逐个计数，overlap 产生的多个相关 Child 不会折叠；`EvidenceGroupRecall@K` 则把这些等价 Child 视为同一事实，命中任意一个即可。两种口径必须同时保留：前者用于与标准 Passage/Chunk 检索评测横向比较，后者用于判断回答证据是否充分。

数据同时标记 `retrieval_scope`、`parent_child_count_bucket`、`difficulty` 和 `query_style`。其中 7 条是与标准版本共享 `intent_id` 的错别字变体，并继承完全相同的数据分区和 Gold。

自动生成只能确认配额、ID 归属和证据文本存在，不能代替业务审核。因此 Query 与 Chunk Gold 统一标记为 `needs_review`。正式跑基准前应逐条核对 Query 自然度、Gold 完整性、Chunk relevance 和推荐型 Query 的全部相关文档，然后改成 `reviewed`。

## 生成与校验

从当前 Chunk 映射重新生成数据：

```bash
.venv/bin/python tests/evaluation-version4/scripts/generate_queries.py
```

该命令会同时生成 `queries.jsonl`、`chunk_gold.jsonl` 和记录两者 SHA-256 的 `manifest.json`。

检查配额、Chunk qrels 和 Document/Parent/Child 层级关系：

```bash
.venv/bin/python tests/evaluation-version4/scripts/validate_queries.py
```

正式评测前执行强制审核检查：

```bash
.venv/bin/python tests/evaluation-version4/scripts/validate_queries.py --require-reviewed
```

同一 `intent_id` 的后续改写必须沿用相同 `dataset_split`，避免意图泄漏到开发集和测试集两边。

## 运行检索评测

默认比较 Dense、Sparse、RRF、`RRF + Parent 扩展` 和生产 Parent-Rerank 路径：

```bash
.venv/bin/python tests/evaluation-version4/scripts/run_evaluation.py
```

开发期间可只跑 RRF 和 Parent-Rerank：

```bash
.venv/bin/python tests/evaluation-version4/scripts/run_evaluation.py \
  --methods hybrid_rrf,hybrid_parent_rerank \
  --dataset-split dev
```

只做 Parent 扩展、不使用 Cross-Encoder 的消融实验使用 `hybrid_parent`。它按 Parent 首次激活顺序排列候选，同 Parent 内按原始 Child 顺序排列：

```bash
.venv/bin/python tests/evaluation-version4/scripts/run_evaluation.py \
  --methods hybrid_rrf,hybrid_parent,hybrid_parent_rerank \
  --dataset-split dev
```

参数矩阵无需改配置文件，可用命令行覆盖。例如初召回 20、最终评估 3/5/10：

```bash
.venv/bin/python tests/evaluation-version4/scripts/run_evaluation.py \
  --initial-top-k 20 \
  --final-top-k 3,5,10 \
  --output tests/evaluation-version4/reports/dev-i20-f3-5-10.json
```

`--query-field rewritten_query` 只读取数据集中已经固定并审核的改写文本，不会在评测时调用 Query Rewrite 模型；默认生成的数据不伪造该字段。

人工审核完成后，测试集的正式命令应增加 `--require-reviewed --dataset-split test`。运行需要本地 Milvus、已导入的评估 Collection、BGE-M3 模型，以及启用 Parent-Rerank 时可用的 Cross-Encoder 配置。

结果写入 `reports/retrieval_eval.json` 和同名 Markdown。每条结果保存：

- `initial`：初始 Child Top-50；
- `activated_parent_ids`：初召回激活的 Parent；
- `expanded`：Parent 扩展后的候选 Child；
- `final`：最终重排 Top-10；
- `latency_ms`：Embedding、检索、扩展、重排和总耗时。

Embedding 按单条 Query 计时；共享的 Hybrid 初召回即使被多个消融方法复用，也沿用首次实际检索耗时，避免 Parent 方法的延迟被缓存错误记为接近零。

标准检索指标为 `ChunkHit@K`、`ChunkRecall@K`、`ChunkPrecision@K`、`ChunkMRR@K` 和 `ChunkNDCG@K`，只在拥有严格 Chunk Gold 的 Query 上做 Macro Average；`ChunkPrecision@K` 的分母固定为 K。架构与回答证据指标继续使用 `ParentActivationRecall@50`、`EvidenceGroupRecall@K` 和 `FullSupportHit@K`。Parent 激活率按唯一必要 Parent 需求计算；同一 Parent 下的多个事实证据组不会重复扩大分母。`AnyEvidenceHit@K` 只表示命中任意一组证据，不能命名为 Chunk Recall。报告会分别按 Query 类型、单/跨 Parent、Parent 子块数、难度和 Query 风格拆分。

`ContextPrecision@5` 使用严格的 `相关 Child 数 / 返回 Child 数`。当某条事实只有一个 Gold Child 时，即使它排第一，该指标最高也只有 `1/5`；因此不能直接套用 60% 的统一验收线，应先按 Query 类型跑开发集基线后分别设阈值。

`POSSIBLE_LABEL_GAP` 只是自动启发式提示，必须人工核对后才能确认是标签遗漏。
