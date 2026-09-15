# 通用检索 Query V2

V2 仅评测能够由局部 Chunk 文本直接提供证据的通用检索意图：

- `dish_name`
- `ingredient`
- `taste_scene`
- `semantic_description`

`negative` 和 `numeric` 不符合当前文档评测需求，已从 Query 数据和生成流程中移除。

`../labels/queries.jsonl` 是当前主数据集，同样只包含以上四类 Query；旧实验结果仅保留在报告目录中。
