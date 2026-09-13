# Dense、Sparse 与 Hybrid 严格 Recall 重算报告

## 评估范围

- 数据集：HowToCook 菜谱检索原始干净 query
- Query：720 条，6 种 query_type，每种 120 条
- 菜谱：120 份；Milvus Collection：`familyos_document_chunks_eval_v1`
- 输入排名：复用 `sparse-dense-all.json` 已保存的真实检索结果，本次未重新调用 Milvus
- 对比方法：Dense、Sparse、4 组 RRF、3 组 Dense/Sparse Weighted Hybrid
- 标签状态：`needs_review`

## 严格 Recall 定义

本报告不再使用“TopK 至少命中一个正样本即记为 1”的 Hit Recall，而是计算：

```text
Strict Recall@K(q) = |TopK(q) 与 Gold(q) 的交集| / |Gold(q)|
Macro Strict Recall@K = 每条 query 的 Strict Recall@K 等权平均
Micro Strict Recall@K = 所有命中正样本数 / 所有 Gold 正样本数
```

Document Gold 通常只有一个，因此 Document Strict Recall 与旧 Document Hit Recall 相同。Chunk Gold 通常有 1 至 2 个，因此 Chunk Strict Recall 会明显低于旧 Chunk Hit Recall。

## 总体 Macro Strict Recall

| 方法 | Doc R@5 | Doc R@10 | Doc R@20 | Chunk R@5 | Chunk R@10 | Chunk R@20 |
|---|---:|---:|---:|---:|---:|---:|
| Dense | 0.7167 | 0.7875 | 0.8278 | 0.4125 | 0.5090 | 0.6056 |
| Sparse | 0.7319 | 0.8222 | 0.8653 | 0.3875 | 0.5028 | 0.5993 |
| RRF k10 | 0.7736 | 0.8417 | 0.8792 | 0.4583 | 0.5646 | 0.6542 |
| RRF k20 | 0.7694 | 0.8486 | 0.8875 | 0.4569 | 0.5611 | 0.6576 |
| RRF k60 | 0.7597 | 0.8444 | 0.8861 | 0.4514 | 0.5583 | 0.6590 |
| RRF k100 | 0.7583 | 0.8458 | 0.8847 | 0.4521 | 0.5583 | 0.6590 |
| Weighted 0.3/0.7 | 0.7625 | 0.8417 | 0.8806 | 0.4569 | 0.5611 | 0.6458 |
| Weighted 0.5/0.5 | 0.7639 | 0.8375 | 0.8708 | 0.4583 | 0.5694 | 0.6493 |
| Weighted 0.7/0.3 | 0.7611 | 0.8403 | 0.8722 | 0.4542 | 0.5653 | 0.6500 |

## 总体 Micro Strict Recall

| 方法 | Doc R@10 | Chunk R@10 |
|---|---:|---:|
| Dense | 0.7875 | 0.5109 |
| Sparse | 0.8222 | 0.5018 |
| RRF k10 | 0.8417 | 0.5646 |
| RRF k20 | 0.8486 | 0.5618 |
| RRF k60 | 0.8444 | 0.5589 |
| RRF k100 | 0.8458 | 0.5589 |
| Weighted 0.3/0.7 | 0.8417 | 0.5618 |
| Weighted 0.5/0.5 | 0.8375 | 0.5702 |
| Weighted 0.7/0.3 | 0.8403 | 0.5660 |

## 分 Query Type 的 Chunk Macro Strict Recall@10

| Query Type | Dense | Sparse | RRF k10 | RRF k20 | RRF k60 | RRF k100 | Weighted 0.3/0.7 | Weighted 0.5/0.5 | Weighted 0.7/0.3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dish_name | 0.7583 | 0.7167 | 0.8083 | 0.8000 | 0.7917 | 0.7958 | 0.7958 | 0.8125 | 0.8250 |
| ingredient | 0.6375 | 0.6167 | 0.6708 | 0.6792 | 0.6792 | 0.6792 | 0.6792 | 0.6958 | 0.6875 |
| negative | 0.4458 | 0.3667 | 0.4792 | 0.4875 | 0.4833 | 0.4792 | 0.4833 | 0.4958 | 0.4958 |
| numeric | 0.4917 | 0.5042 | 0.5542 | 0.5458 | 0.5458 | 0.5458 | 0.5458 | 0.5500 | 0.5458 |
| semantic_description | 0.4167 | 0.4500 | 0.4833 | 0.4750 | 0.4708 | 0.4708 | 0.4833 | 0.4667 | 0.4500 |
| taste_scene | 0.3042 | 0.3625 | 0.3917 | 0.3792 | 0.3792 | 0.3792 | 0.3792 | 0.3958 | 0.3875 |

## 分 Query Type 的 Document Macro Strict Recall@10

| Query Type | Dense | Sparse | RRF k10 | RRF k20 | RRF k60 | RRF k100 | Weighted 0.3/0.7 | Weighted 0.5/0.5 | Weighted 0.7/0.3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dish_name | 0.9417 | 1.0000 | 1.0000 | 1.0000 | 0.9917 | 0.9917 | 1.0000 | 0.9833 | 0.9833 |
| ingredient | 0.8833 | 0.9167 | 0.9250 | 0.9250 | 0.9167 | 0.9167 | 0.9250 | 0.9000 | 0.9000 |
| negative | 0.7000 | 0.6917 | 0.7333 | 0.7750 | 0.7583 | 0.7667 | 0.7583 | 0.7333 | 0.7500 |
| numeric | 0.7417 | 0.7750 | 0.8167 | 0.8167 | 0.8333 | 0.8250 | 0.8083 | 0.8250 | 0.8167 |
| semantic_description | 0.7333 | 0.8083 | 0.8000 | 0.7917 | 0.7750 | 0.7833 | 0.7833 | 0.7667 | 0.7583 |
| taste_scene | 0.7250 | 0.7417 | 0.7750 | 0.7833 | 0.7917 | 0.7917 | 0.7750 | 0.8167 | 0.8333 |

## 方法选择结论

- Document Macro Strict Recall@10 最高：RRF k20，0.8486。
- Chunk Macro Strict Recall@10 最高：Weighted 0.5/0.5，0.5694。
- Chunk Macro Strict Recall@20 最高：RRF k60 与 RRF k100，并列 0.6590。
- 明确菜名的 Chunk Recall@10 最高：Weighted 0.7/0.3，0.8250。
- 食材查询的 Chunk Recall@10 最高：Weighted 0.5/0.5，0.6958。
- 否定查询的 Chunk Recall@10 最高：Weighted 0.5/0.5 与 0.7/0.3，并列 0.4958。
- 数字查询的 Chunk Recall@10 最高：RRF k10，0.5542。
- 语义描述的 Chunk Recall@10 最高：RRF k10 与 Weighted 0.3/0.7，并列 0.4833。
- 口味场景的 Chunk Recall@10 最高：Weighted 0.5/0.5，0.3958。

严格口径下，没有一种融合参数在所有目标上同时最优。若优先保证找到正确菜谱，RRF k20 更合适；若优先找全正确证据块，Weighted 0.5/0.5 更合适；当前 RRF k60 在 Top20 证据覆盖上更稳定。

## 旧口径与严格口径对比

以当前线上基线 RRF k60 为例：

| 指标 | 旧 Hit Recall | Macro Strict Recall | 差值 |
|---|---:|---:|---:|
| Document Recall@10 | 0.8444 | 0.8444 | +0.0000 |
| Chunk Recall@10 | 0.7153 | 0.5583 | -0.1569 |

## 说明

- 本次只重新计算 Recall，不改变检索排名，因此可以直接比较不同方法的证据覆盖能力。
- Macro Strict Recall 是本报告的主要口径；Micro 指标用于观察按 Gold 数量加权后的整体覆盖。
- Document 正样本通常只有一个，所以其严格 Recall 与旧报告基本一致。
- Chunk Strict Recall 更适合评估 RAG 是否找全所需证据，但仍依赖当前 `needs_review` 标签质量。
- 本报告不包含 Query Rewrite、Graph 路由和生成回答，只比较干净 query 上的 Dense、Sparse 与 Hybrid。
