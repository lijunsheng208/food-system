"""Python Agent 与现有 Go 服务共享的稳定协议常量。"""

DOCUMENT_INDEX_EVENT_TYPE = "document.index.requested"
DOCUMENT_INDEX_SCHEMA_VERSION = 1
GET_DOCUMENT_DOWNLOAD_TICKET_METHOD = "/knowledge.v1.KnowledgeInternalService/GetDocumentDownloadTicket"
COMPLETE_DOCUMENT_INDEX_METHOD = "/knowledge.v1.KnowledgeInternalService/CompleteDocumentIndex"
FAIL_DOCUMENT_INDEX_METHOD = "/knowledge.v1.KnowledgeInternalService/FailDocumentIndex"
INTERNAL_TOKEN_HEADER = "x-familyos-internal-token"
