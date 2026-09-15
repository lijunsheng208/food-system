# Retrieval Evaluation V4

- Query 数：300
- 数据分区：`all`
- Query 字段：`query`
- 初召回 Top-K：50
- 最终 Top-K：[5, 10]
- Agent / 回答模型：未调用

## 总体对比

| 方法 | Initial Doc Hit | Initial Chunk Recall@50 | Parent Activation | Final Doc Hit@10 | Chunk Recall@10 | Chunk MRR@10 | Evidence Recall@10 | Full Support@10 | Context Precision@5 | Constraint Violation@10 | Total P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dense | 0.9655 | 0.9573 | 0.9590 | 0.9172 | 0.8803 | 0.5508 | 0.8821 | 0.8462 | 0.2041 | 0.9139 | 93.2890 |
| sparse | 0.9862 | 0.8949 | 0.8974 | 0.9414 | 0.7701 | 0.4284 | 0.7744 | 0.7436 | 0.1723 | 0.9351 | 91.0812 |
| hybrid_rrf | 0.9828 | 0.9564 | 0.9564 | 0.9448 | 0.8496 | 0.5029 | 0.8538 | 0.8308 | 0.2031 | 0.8934 | 91.7095 |
| hybrid_parent_rerank | 0.9828 | 0.9564 | 0.9564 | 0.9517 | 0.9179 | 0.7144 | 0.9205 | 0.9077 | 0.2256 | 0.8691 | 927.4601 |

## dense / Query 类型

| Query 类型 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| calculation_fact | 0.9778 | 0.9111 | 0.9778 | 0.9111 | 0.9111 |
| constraint | 0.4500 | - | - | - | - |
| cross_parent | 1.0000 | 0.8500 | 0.9667 | 0.8500 | 0.7333 |
| dish_lookup | 0.9667 | - | - | - | - |
| ingredient_fact | 0.9556 | 0.8815 | 0.9333 | 0.8889 | 0.8889 |
| procedure_fact | 1.0000 | 0.8889 | 0.9556 | 0.8889 | 0.8889 |
| recommendation | 0.8000 | - | - | - | - |
| unanswerable | - | - | - | - | - |

## dense / 检索范围

| 检索范围 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| cross_parent | 1.0000 | 0.8500 | 0.9667 | 0.8500 | 0.7333 |
| document_only | 0.7789 | - | - | - | - |
| single_parent | 0.9778 | 0.8938 | 0.9556 | 0.8963 | 0.8963 |

## dense / Parent 子块数

| Parent 子块数 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| 1 | 0.9838 | 0.8793 | 0.9568 | 0.8811 | 0.8486 |
| >1 | 1.0000 | 0.9000 | 1.0000 | 0.9000 | 0.8000 |
| not_applicable | 0.7789 | - | - | - | - |

## dense / 难度

| 难度 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| easy | 0.9600 | 0.8815 | 0.9333 | 0.8889 | 0.8889 |
| hard | 0.8400 | 0.8500 | 0.9667 | 0.8500 | 0.7333 |
| medium | 0.9889 | 0.9000 | 0.9667 | 0.9000 | 0.9000 |

## dense / Query 风格

| Query 风格 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| colloquial | 0.9708 | 0.8366 | 0.9369 | 0.8398 | 0.8058 |
| standard | 0.8767 | 0.9261 | 0.9830 | 0.9261 | 0.8864 |
| typo | 0.7143 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## sparse / Query 类型

| Query 类型 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| calculation_fact | 1.0000 | 0.7778 | 0.8889 | 0.7778 | 0.7778 |
| constraint | 0.4500 | - | - | - | - |
| cross_parent | 1.0000 | 0.8167 | 0.9500 | 0.8167 | 0.7167 |
| dish_lookup | 1.0000 | - | - | - | - |
| ingredient_fact | 1.0000 | 0.6481 | 0.8000 | 0.6667 | 0.6667 |
| procedure_fact | 1.0000 | 0.8222 | 0.9333 | 0.8222 | 0.8222 |
| recommendation | 0.8667 | - | - | - | - |
| unanswerable | - | - | - | - | - |

## sparse / 检索范围

| 检索范围 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| cross_parent | 1.0000 | 0.8167 | 0.9500 | 0.8167 | 0.7167 |
| document_only | 0.8211 | - | - | - | - |
| single_parent | 1.0000 | 0.7494 | 0.8741 | 0.7556 | 0.7556 |

## sparse / Parent 子块数

| Parent 子块数 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| 1 | 1.0000 | 0.7604 | 0.8919 | 0.7649 | 0.7351 |
| >1 | 1.0000 | 0.9500 | 1.0000 | 0.9500 | 0.9000 |
| not_applicable | 0.8211 | - | - | - | - |

## sparse / 难度

| 难度 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| easy | 1.0000 | 0.6481 | 0.8000 | 0.6667 | 0.6667 |
| hard | 0.8640 | 0.8167 | 0.9500 | 0.8167 | 0.7167 |
| medium | 1.0000 | 0.8000 | 0.9111 | 0.8000 | 0.8000 |

## sparse / Query 风格

| Query 风格 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| colloquial | 0.9854 | 0.7201 | 0.8544 | 0.7233 | 0.6796 |
| standard | 0.9110 | 0.8182 | 0.9432 | 0.8239 | 0.8068 |
| typo | 0.7143 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## hybrid_rrf / Query 类型

| Query 类型 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| calculation_fact | 1.0000 | 0.8667 | 1.0000 | 0.8667 | 0.8667 |
| constraint | 0.6500 | - | - | - | - |
| cross_parent | 1.0000 | 0.8750 | 0.9583 | 0.8750 | 0.8000 |
| dish_lookup | 1.0000 | - | - | - | - |
| ingredient_fact | 0.9556 | 0.7815 | 0.9111 | 0.8000 | 0.8000 |
| procedure_fact | 1.0000 | 0.8667 | 0.9556 | 0.8667 | 0.8667 |
| recommendation | 0.8444 | - | - | - | - |
| unanswerable | - | - | - | - | - |

## hybrid_rrf / 检索范围

| 检索范围 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| cross_parent | 1.0000 | 0.8750 | 0.9583 | 0.8750 | 0.8000 |
| document_only | 0.8526 | - | - | - | - |
| single_parent | 0.9852 | 0.8383 | 0.9556 | 0.8444 | 0.8444 |

## hybrid_rrf / Parent 子块数

| Parent 子块数 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| 1 | 0.9892 | 0.8441 | 0.9541 | 0.8486 | 0.8270 |
| >1 | 1.0000 | 0.9500 | 1.0000 | 0.9500 | 0.9000 |
| not_applicable | 0.8526 | - | - | - | - |

## hybrid_rrf / 难度

| 难度 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| easy | 0.9733 | 0.7815 | 0.9111 | 0.8000 | 0.8000 |
| hard | 0.8880 | 0.8750 | 0.9583 | 0.8750 | 0.8000 |
| medium | 1.0000 | 0.8667 | 0.9778 | 0.8667 | 0.8667 |

## hybrid_rrf / Query 风格

| Query 风格 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| colloquial | 0.9635 | 0.8026 | 0.9272 | 0.8058 | 0.7767 |
| standard | 0.9315 | 0.8977 | 0.9886 | 0.9034 | 0.8864 |
| typo | 0.8571 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## hybrid_parent_rerank / Query 类型

| Query 类型 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| calculation_fact | 1.0000 | 0.9556 | 1.0000 | 0.9556 | 0.9556 |
| constraint | 0.6500 | - | - | - | - |
| cross_parent | 0.9667 | 0.9083 | 0.9583 | 0.9083 | 0.8667 |
| dish_lookup | 1.0000 | - | - | - | - |
| ingredient_fact | 1.0000 | 0.9000 | 0.9111 | 0.9111 | 0.9111 |
| procedure_fact | 0.9556 | 0.9111 | 0.9556 | 0.9111 | 0.9111 |
| recommendation | 0.9333 | - | - | - | - |
| unanswerable | - | - | - | - | - |

## hybrid_parent_rerank / 检索范围

| 检索范围 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| cross_parent | 0.9667 | 0.9083 | 0.9583 | 0.9083 | 0.8667 |
| document_only | 0.8947 | - | - | - | - |
| single_parent | 0.9852 | 0.9222 | 0.9556 | 0.9259 | 0.9259 |

## hybrid_parent_rerank / Parent 子块数

| Parent 子块数 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| 1 | 0.9784 | 0.9162 | 0.9541 | 0.9189 | 0.9081 |
| >1 | 1.0000 | 0.9500 | 1.0000 | 0.9500 | 0.9000 |
| not_applicable | 0.8947 | - | - | - | - |

## hybrid_parent_rerank / 难度

| 难度 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| easy | 1.0000 | 0.9000 | 0.9111 | 0.9111 | 0.9111 |
| hard | 0.9040 | 0.9083 | 0.9583 | 0.9083 | 0.8667 |
| medium | 0.9778 | 0.9333 | 0.9778 | 0.9333 | 0.9333 |

## hybrid_parent_rerank / Query 风格

| Query 风格 | Doc Hit@10 | Chunk Recall@10 | Parent Activation@50 | Evidence Recall@10 | Full Support@10 |
|---|---:|---:|---:|---:|---:|
| colloquial | 0.9781 | 0.8883 | 0.9272 | 0.8883 | 0.8738 |
| standard | 0.9315 | 0.9489 | 0.9886 | 0.9545 | 0.9432 |
| typo | 0.8571 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
