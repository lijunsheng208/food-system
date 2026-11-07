# Milvus 检索离线评估报告

- 查询数：720
- 来源菜谱数：120
- 来源类别数：6（aquatic, breakfast, meat_dish, soup, staple, vegetable_dish）
- Collection：`familyos_document_chunks_eval_v1`
- 标签状态：`['needs_review']`

- ANN 每路候选数：100，Parent 扩展前融合候选数：100
- Query 字段：`query`
- 约束解析覆盖：Numeric 120/120，Negative 90/120

## 总体对比

| 方法 | Doc R@5 | Doc R@10 | Doc MRR@10 | Doc NDCG@10 | Chunk R@10 | HardNeg Hit@10 | HardNeg 首次排名 | HardNeg 平均排名 | 约束满足@10 | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dense | 0.7389 | 0.8125 | 0.6205 | 0.6667 | 0.6750 | 0.4111 | 8.22 | 9.36 | 0.4479 | 5.68 |
| sparse | 0.7319 | 0.8222 | 0.5929 | 0.6479 | 0.6542 | 0.4222 | 8.22 | 9.42 | 0.3983 | 6.35 |
| hybrid_rrf_k60 | 0.7653 | 0.8500 | 0.6408 | 0.6908 | 0.7125 | 0.4431 | 8.00 | 9.25 | 0.4171 | 6.02 |
| hybrid_rrf_k60_parent_rerank | 0.8417 | 0.9042 | 0.7183 | 0.7634 | 0.8153 | 0.4319 | 8.01 | 9.21 | 0.4976 | 1478.49 |
| hybrid_rrf_k60_constraint_parent_rerank | 0.8444 | 0.8958 | 0.7211 | 0.7635 | 0.8056 | 0.4028 | 8.18 | 9.33 | 0.6222 | 1250.41 |

## 分 query_type 指标

| 方法 | query_type | Doc R@10 | Doc MRR@10 | Doc NDCG@10 | Chunk R@10 | HardNeg 首次排名 | HardNeg 平均排名 | 约束满足@10 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| dense | dish_name | 0.9917 | 0.9750 | 0.9794 | 0.9333 | 8.22 | 9.32 | - |
| dense | ingredient | 0.8833 | 0.7453 | 0.7790 | 0.7833 | 8.01 | 9.21 | - |
| dense | negative | 0.7417 | 0.4781 | 0.5410 | 0.6333 | 8.37 | 9.52 | 0.5975 |
| dense | numeric | 0.7500 | 0.4993 | 0.5604 | 0.6417 | 8.15 | 9.30 | 0.2983 |
| dense | semantic_description | 0.7333 | 0.5100 | 0.5631 | 0.6167 | 8.30 | 9.37 | - |
| dense | taste_scene | 0.7750 | 0.5153 | 0.5775 | 0.4417 | 8.25 | 9.43 | - |
| sparse | dish_name | 1.0000 | 0.9875 | 0.9908 | 0.8750 | 8.07 | 9.35 | - |
| sparse | ingredient | 0.9167 | 0.7095 | 0.7608 | 0.7417 | 8.11 | 9.38 | - |
| sparse | negative | 0.6917 | 0.4522 | 0.5089 | 0.4833 | 8.67 | 9.67 | 0.5025 |
| sparse | numeric | 0.7750 | 0.4568 | 0.5337 | 0.6250 | 7.93 | 9.20 | 0.2942 |
| sparse | semantic_description | 0.8083 | 0.4628 | 0.5442 | 0.6417 | 7.98 | 9.29 | - |
| sparse | taste_scene | 0.7417 | 0.4888 | 0.5488 | 0.5583 | 8.54 | 9.65 | - |
| hybrid_rrf_k60 | dish_name | 1.0000 | 0.9887 | 0.9914 | 0.9167 | 7.90 | 9.18 | - |
| hybrid_rrf_k60 | ingredient | 0.9167 | 0.7824 | 0.8156 | 0.8167 | 7.72 | 9.08 | - |
| hybrid_rrf_k60 | negative | 0.7667 | 0.4800 | 0.5478 | 0.6667 | 8.21 | 9.36 | 0.5300 |
| hybrid_rrf_k60 | numeric | 0.8167 | 0.5366 | 0.6031 | 0.6583 | 7.77 | 9.08 | 0.3042 |
| hybrid_rrf_k60 | semantic_description | 0.8000 | 0.5249 | 0.5912 | 0.6833 | 8.04 | 9.29 | - |
| hybrid_rrf_k60 | taste_scene | 0.8000 | 0.5325 | 0.5959 | 0.5333 | 8.38 | 9.49 | - |
| hybrid_rrf_k60_parent_rerank | dish_name | 0.9917 | 0.8751 | 0.9042 | 0.9417 | 8.18 | 9.32 | - |
| hybrid_rrf_k60_parent_rerank | ingredient | 0.9500 | 0.8191 | 0.8515 | 0.8833 | 7.80 | 9.04 | - |
| hybrid_rrf_k60_parent_rerank | negative | 0.8750 | 0.6441 | 0.6990 | 0.7750 | 8.47 | 9.52 | 0.6360 |
| hybrid_rrf_k60_parent_rerank | numeric | 0.8583 | 0.6869 | 0.7291 | 0.8083 | 7.88 | 9.10 | 0.3591 |
| hybrid_rrf_k60_parent_rerank | semantic_description | 0.8500 | 0.5798 | 0.6439 | 0.7167 | 7.89 | 9.07 | - |
| hybrid_rrf_k60_parent_rerank | taste_scene | 0.9000 | 0.7052 | 0.7526 | 0.7667 | 7.84 | 9.20 | - |
| hybrid_rrf_k60_constraint_parent_rerank | dish_name | 0.9917 | 0.8751 | 0.9042 | 0.9417 | 8.18 | 9.32 | - |
| hybrid_rrf_k60_constraint_parent_rerank | ingredient | 0.9500 | 0.8191 | 0.8515 | 0.8833 | 7.80 | 9.04 | - |
| hybrid_rrf_k60_constraint_parent_rerank | negative | 0.9000 | 0.6645 | 0.7207 | 0.7917 | 8.78 | 9.73 | 0.7848 |
| hybrid_rrf_k60_constraint_parent_rerank | numeric | 0.7833 | 0.6832 | 0.7084 | 0.7333 | 8.59 | 9.60 | 0.4595 |
| hybrid_rrf_k60_constraint_parent_rerank | semantic_description | 0.8500 | 0.5798 | 0.6439 | 0.7167 | 7.89 | 9.07 | - |
| hybrid_rrf_k60_constraint_parent_rerank | taste_scene | 0.9000 | 0.7052 | 0.7526 | 0.7667 | 7.84 | 9.20 | - |
