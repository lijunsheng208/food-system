# 多轮上下文压缩 A/B 评测

| 指标 | 固定窗口 | 滚动摘要 |
|---|---:|---:|
| 关键事实命中率 | 0.0% (0/8) | 100.0% (8/8) |
| 总输入 Token（含摘要调用） | 304 | 964 |
| 总输出 Token（含摘要调用） | 692 | 2550 |
| 输入文本估算 Token | 199 | 479 |

## 逐项结果

| 基准项 | 固定窗口 | 滚动摘要 |
|---|---|---|
| allergy_peanut | 未命中 | 命中 |
| avoid_cilantro | 未命中 | 命中 |
| serving_count | 未命中 | 命中 |
| spice_preference | 未命中 | 命中 |
| cuisine_preference | 未命中 | 命中 |
| dietary_constraint | 未命中 | 命中 |
| correction_latest | 未命中 | 命中 |
| pending_item | 未命中 | 命中 |

注：事实命中按预先定义的关键词规则计算；输入 Token 同时报模型 usage 与文本估算，便于发现兼容接口未返回 usage 的情况。
