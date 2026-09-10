USE familyos_agent;

-- Python Agent 保存父块和子块；父块仅供生成阶段使用，子块进入向量和 BM25 索引。
ALTER TABLE agent_document_chunk
    ADD COLUMN chunk_type TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '0父块 1子块' AFTER index_version,
    ADD COLUMN parent_id CHAR(36) NULL COMMENT '子块所属父块ID；父块为空' AFTER chunk_type,
    ADD KEY idx_agent_document_chunk_parent (parent_id),
    ADD CONSTRAINT chk_agent_document_chunk_type CHECK (chunk_type IN (0, 1));

-- 保证同一文档版本内父块和子块序号独立，父子映射由 parent_id 表示。
ALTER TABLE agent_document_chunk
    DROP INDEX uk_agent_document_chunk_version,
    ADD UNIQUE KEY uk_agent_document_chunk_version_type (document_id, index_version, chunk_type, chunk_index);

