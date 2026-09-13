# 菜谱检索离线评测

评测代码、原始 Chunk 映射、查询标签和实验报告按职责分开保存。查询由已导入的 Markdown Chunk 确定性生成，生成时会校验正例证据、来源覆盖和约束字段，避免把菜名模板的高召回误认为检索质量。

## 数据集设计

当前查询集覆盖 6 个类别、120 篇菜谱，每篇生成 6 条查询，共 720 条：

| query_type | 目的 | 主要证据 |
|---|---|---|
| `dish_name` | 已知菜名召回 | 菜名、原料和关键步骤 |
| `ingredient` | 原料词面检索 | 原料清单和操作 |
| `taste_scene` | 口味、口感和场景泛化 | 菜谱简介和完成状态 |
| `semantic_description` | 不依赖菜名的做法描述 | 操作步骤和技法 |
| `negative` | 排除原料或技法 | `forbidden_terms`、`constraint_type` |
| `numeric` | 时间、温度、用量和热量约束 | `numeric_constraints` |

`dish_name` 可以包含目标菜名；其余类型会尽量去掉目标菜名。`negative` 的正例全文不包含 `forbidden_terms`，`numeric` 的数值来自正例 Chunk 中的真实数值。每条记录还保留 2 个从完整 370 篇语料中选出的相似 hard negative 及选择原因。

主要字段示例：

```json
{
  "query_type": "negative",
  "source_category": "soup",
  "positive_documents": [123],
  "positive_chunks": ["chunk-id"],
  "hard_negative_documents": [456, 789],
  "forbidden_terms": ["花生"],
  "constraint_type": "ingredient_absence",
  "numeric_constraints": [],
  "label_status": "needs_review"
}
```

数值约束使用统一单位：`minutes`、`temperature_c`、`grams`、`milliliters`、`calories`。支持 `eq`、`<=`、`>=` 和 `between`。

## 生成和校验

先确保 `datasets/raw/chunks.jsonl` 是由评估 Collection 导出的最新 Chunk 映射，然后运行：

```bash
cd agent-python-service
.venv/bin/python evaluation/scripts/generate_queries.py \
  --mapping evaluation/datasets/raw/chunks.jsonl \
  --output evaluation/datasets/labels/queries.jsonl
```

生成器默认每类选择 20 篇菜谱。它会在写文件前检查来源至少 100 篇、类别至少 6 个、六种类型数量均衡、正例 Chunk 所属文档正确、hard negative 不与正例重叠、否定词确实缺失以及数值证据存在。标签仍为 `needs_review`，人工确认后再改为 `reviewed`。

如需先重建隔离 Collection：

```bash
.venv/bin/python -m evaluation.scripts.import_dishes \
  --root /Users/lijunsheng/Documents/postgraduate/HowToCook-master/dishes \
  --config config/config.yaml \
  --recreate
```

## 评测指标

`run_retrieval_eval.py` 对 Dense、Sparse、Milvus RRF 和 Weighted Hybrid 使用同一批向量和过滤条件，输出 JSON 与 Markdown 报告。除 Document/Chunk Recall@5/@10/@20 外，报告还包括：

- `document_mrr@10`、`document_ndcg@10`：正确文档的排序质量；
- `chunk_recall@10`：答案所在 Chunk 是否进入 Top10；
- `hard_negative_hit@10`：相似错误文档是否进入 Top10；
- `hard_negative_first_rank@10`、`hard_negative_mean_rank@10`：hard negative 的首次和平均排名，未命中按 11 计；
- `constraint_satisfaction@10`：negative/numeric 查询的 Top10 文档满足结构化约束的比例；
- P50/P95 检索延迟。

报告会按 `query_type` 分开统计 `Document Recall@10`、MRR、NDCG、Chunk Recall、hard negative 排名和约束满足率，不再把菜名、原料、语义和约束查询混为一组。

真实运行前提是本地 Milvus 已启动、评估 Collection 使用与生产一致的字段和向量配置。没有 Milvus 时只生成和审核标签，不伪造检索结果。
