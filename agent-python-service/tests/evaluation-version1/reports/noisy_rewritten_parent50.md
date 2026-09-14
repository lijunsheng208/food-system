# Milvus 检索离线评估报告

- 查询数：720
- 来源菜谱数：120
- 来源类别数：6（aquatic, breakfast, meat_dish, soup, staple, vegetable_dish）
- Collection：`familyos_document_chunks_eval_v1`
- 标签状态：`['needs_review']`

## 总体对比

| 方法 | Doc R@5 | Doc R@10 | Doc MRR@10 | Doc NDCG@10 | Chunk R@10 | HardNeg Hit@10 | HardNeg 首次排名 | HardNeg 平均排名 | 约束满足@10 | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dense | 0.7139 | 0.7833 | 0.5869 | 0.6344 | 0.6542 | 0.3917 | 8.27 | 9.39 | 0.4567 | 2.82 |
| sparse | 0.7292 | 0.8083 | 0.5916 | 0.6433 | 0.6500 | 0.4042 | 8.29 | 9.44 | 0.3985 | 1.26 |
| hybrid_rrf_k60 | 0.7694 | 0.8347 | 0.6237 | 0.6747 | 0.6986 | 0.4250 | 8.03 | 9.26 | 0.4275 | 2.46 |
| hybrid_rrf_k60_parent_rerank | 0.8167 | 0.8597 | 0.6868 | 0.7292 | 0.7611 | 0.4250 | 8.05 | 9.26 | 0.4518 | 458.71 |

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
| hybrid_rrf_k60 | dish_name | 1.0000 | 0.9575 | 0.9678 | 0.9000 | 7.88 | 9.21 | - |
| hybrid_rrf_k60 | ingredient | 0.9083 | 0.7713 | 0.8054 | 0.8167 | 8.01 | 9.19 | - |
| hybrid_rrf_k60 | negative | 0.7333 | 0.4809 | 0.5421 | 0.6500 | 8.19 | 9.44 | 0.5585 |
| hybrid_rrf_k60 | numeric | 0.7667 | 0.4755 | 0.5454 | 0.6083 | 7.87 | 9.15 | 0.2964 |
| hybrid_rrf_k60 | semantic_description | 0.7750 | 0.5246 | 0.5852 | 0.6667 | 8.12 | 9.25 | - |
| hybrid_rrf_k60 | taste_scene | 0.8250 | 0.5322 | 0.6022 | 0.5500 | 8.11 | 9.32 | - |
| hybrid_rrf_k60_parent_rerank | dish_name | 0.9917 | 0.8919 | 0.9176 | 0.9333 | 7.97 | 9.19 | - |
| hybrid_rrf_k60_parent_rerank | ingredient | 0.9333 | 0.8122 | 0.8421 | 0.8750 | 7.66 | 8.98 | - |
| hybrid_rrf_k60_parent_rerank | negative | 0.7583 | 0.5955 | 0.6348 | 0.7333 | 8.35 | 9.55 | 0.5912 |
| hybrid_rrf_k60_parent_rerank | numeric | 0.8000 | 0.6325 | 0.6732 | 0.7083 | 7.90 | 9.18 | 0.3124 |
| hybrid_rrf_k60_parent_rerank | semantic_description | 0.8000 | 0.5371 | 0.6013 | 0.6750 | 8.29 | 9.33 | - |
| hybrid_rrf_k60_parent_rerank | taste_scene | 0.8750 | 0.6519 | 0.7059 | 0.6417 | 8.11 | 9.35 | - |
