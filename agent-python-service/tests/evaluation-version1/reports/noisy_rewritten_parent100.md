# Milvus 检索离线评估报告

- 查询数：720
- 来源菜谱数：120
- 来源类别数：6（aquatic, breakfast, meat_dish, soup, staple, vegetable_dish）
- Collection：`familyos_document_chunks_eval_v1`
- 标签状态：`['needs_review']`

## 总体对比

| 方法 | Doc R@5 | Doc R@10 | Doc MRR@10 | Doc NDCG@10 | Chunk R@10 | HardNeg Hit@10 | HardNeg 首次排名 | HardNeg 平均排名 | 约束满足@10 | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dense | 0.7139 | 0.7833 | 0.5869 | 0.6344 | 0.6542 | 0.3917 | 8.27 | 9.39 | 0.4567 | 1.90 |
| sparse | 0.7292 | 0.8083 | 0.5916 | 0.6433 | 0.6500 | 0.4042 | 8.29 | 9.44 | 0.3985 | 1.23 |
| hybrid_rrf_k60 | 0.7708 | 0.8431 | 0.6268 | 0.6790 | 0.6958 | 0.4194 | 8.04 | 9.26 | 0.4271 | 2.98 |
| hybrid_rrf_k60_parent_rerank | 0.8153 | 0.8597 | 0.6921 | 0.7331 | 0.7611 | 0.4347 | 8.04 | 9.26 | 0.4409 | 448.11 |

## 分 query_type 指标

| 方法 | query_type | Doc R@10 | Doc MRR@10 | Doc NDCG@10 | Chunk R@10 | HardNeg 首次排名 | HardNeg 平均排名 | 约束满足@10 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| dense | dish_name | 0.9583 | 0.8984 | 0.9134 | 0.9083 | 8.18 | 9.26 | - |
| dense | ingredient | 0.8750 | 0.7323 | 0.7681 | 0.8000 | 8.02 | 9.22 | - |
| dense | negative | 0.6750 | 0.4613 | 0.5124 | 0.5917 | 8.53 | 9.62 | 0.6273 |
| dense | numeric | 0.7417 | 0.4821 | 0.5449 | 0.6083 | 8.22 | 9.42 | 0.2860 |
| dense | semantic_description | 0.7083 | 0.4697 | 0.5267 | 0.5667 | 8.50 | 9.50 | - |
| dense | taste_scene | 0.7417 | 0.4777 | 0.5406 | 0.4500 | 8.15 | 9.32 | - |
| sparse | dish_name | 1.0000 | 0.9561 | 0.9671 | 0.8667 | 8.19 | 9.41 | - |
| sparse | ingredient | 0.9000 | 0.7259 | 0.7679 | 0.7667 | 7.88 | 9.16 | - |
| sparse | negative | 0.7000 | 0.4500 | 0.5087 | 0.4917 | 8.76 | 9.71 | 0.5089 |
| sparse | numeric | 0.7250 | 0.4339 | 0.5030 | 0.5500 | 8.22 | 9.43 | 0.2882 |
| sparse | semantic_description | 0.7750 | 0.4855 | 0.5551 | 0.6500 | 8.20 | 9.35 | - |
| sparse | taste_scene | 0.7500 | 0.4981 | 0.5582 | 0.5750 | 8.48 | 9.60 | - |
| hybrid_rrf_k60 | dish_name | 1.0000 | 0.9705 | 0.9778 | 0.9000 | 7.78 | 9.17 | - |
| hybrid_rrf_k60 | ingredient | 0.9083 | 0.7706 | 0.8047 | 0.8083 | 7.97 | 9.18 | - |
| hybrid_rrf_k60 | negative | 0.7417 | 0.4850 | 0.5470 | 0.6500 | 8.20 | 9.43 | 0.5584 |
| hybrid_rrf_k60 | numeric | 0.7833 | 0.4787 | 0.5519 | 0.6083 | 7.95 | 9.20 | 0.2959 |
| hybrid_rrf_k60 | semantic_description | 0.8083 | 0.5286 | 0.5956 | 0.6583 | 8.13 | 9.25 | - |
| hybrid_rrf_k60 | taste_scene | 0.8167 | 0.5277 | 0.5970 | 0.5500 | 8.18 | 9.36 | - |
| hybrid_rrf_k60_parent_rerank | dish_name | 0.9917 | 0.9014 | 0.9247 | 0.9333 | 8.12 | 9.28 | - |
| hybrid_rrf_k60_parent_rerank | ingredient | 0.9417 | 0.8027 | 0.8367 | 0.8667 | 7.75 | 9.00 | - |
| hybrid_rrf_k60_parent_rerank | negative | 0.7833 | 0.6292 | 0.6667 | 0.7333 | 7.93 | 9.33 | 0.5758 |
| hybrid_rrf_k60_parent_rerank | numeric | 0.7917 | 0.6179 | 0.6599 | 0.7000 | 8.10 | 9.26 | 0.3061 |
| hybrid_rrf_k60_parent_rerank | semantic_description | 0.8000 | 0.5427 | 0.6057 | 0.7000 | 8.28 | 9.33 | - |
| hybrid_rrf_k60_parent_rerank | taste_scene | 0.8500 | 0.6587 | 0.7048 | 0.6333 | 8.07 | 9.34 | - |
