import api from './api';

export interface UploadTicket {
  document_id: number;
  upload_session_id: string;
  upload_url: string;
  method: 'PUT';
  required_headers: Record<string, string>;
  expires_at: string;
}

// ensurePersonalKnowledgeBase 获取或创建当前用户的个人知识库。
export async function ensurePersonalKnowledgeBase(): Promise<number> {
  const { data } = await api.get<{ code: number; message: string; knowledge_base_id: number }>('/knowledge-bases/personal');
  if (data.code !== 0 || !data.knowledge_base_id) throw new Error(data.message || '获取个人知识库失败');
  return data.knowledge_base_id;
}

// createUploadTicket 向后端申请单文件 OSS 直传授权。
export async function createUploadTicket(knowledgeBaseId: number, params: { filename: string; content_type: string; file_size: number }): Promise<UploadTicket> {
  const { data } = await api.post<{ code: number; message: string; data: UploadTicket }>(`/knowledge-bases/${knowledgeBaseId}/documents/upload-ticket`, params);
  if (data.code !== 0) throw new Error(data.message || '申请上传授权失败');
  return data.data;
}

// uploadDocumentToOSS 将文件二进制直传到后端签发的 OSS 地址。
export async function uploadDocumentToOSS(ticket: UploadTicket, uri: string, contentType: string): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('PUT', ticket.upload_url);
    Object.entries({ ...ticket.required_headers, 'Content-Type': contentType }).forEach(([key, value]) => request.setRequestHeader(key, value));
    request.onload = () => request.status >= 200 && request.status < 300 ? resolve() : reject(new Error(`文件上传失败（${request.status}）`));
    request.onerror = () => reject(new Error('文件上传失败'));
    request.send({ uri, type: contentType, name: 'upload' } as unknown as XMLHttpRequestBodyInit);
  });
}

// completeDocumentUpload 通知后端校验 OSS 对象并提交索引任务。
export async function completeDocumentUpload(documentId: number): Promise<void> {
  const { data } = await api.post<{ code: number; message: string }>(`/knowledge-documents/${documentId}/complete-upload`, {});
  if (data.code !== 0) throw new Error(data.message || '确认上传失败');
}
