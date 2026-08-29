import api from './api';
import { getAccessToken } from './api';
import { API_BASE_URL } from '../config';

export interface UploadTicket {
  document_id: number;
  upload_session_id: string;
  upload_url: string;
  method: 'PUT';
  required_headers: Record<string, string>;
  expires_at: string;
}

export interface DocumentStatusEvent {
  document_id: number;
  status: number;
  index_version: number;
}

export interface DocumentStatusSubscription {
  close: () => void;
}

export interface KnowledgeDocumentItem {
  document_id: number;
  filename: string;
  file_size: number;
  status: number;
  index_version: number;
  created_at: string;
}

export interface DocumentViewTicket {
  document_id: number;
  view_url: string;
  filename: string;
  content_type: string;
  expires_at: string;
}

// ensurePersonalKnowledgeBase 获取或创建当前用户的个人知识库。
export async function ensurePersonalKnowledgeBase(): Promise<number> {
  const { data } = await api.get<{ code: number; message: string; knowledge_base_id: number }>('/knowledge-bases/personal');
  if (data.code !== 0 || !data.knowledge_base_id) throw new Error(data.message || '获取个人知识库失败');
  return data.knowledge_base_id;
}

// listKnowledgeDocuments 查询个人知识库中已有的文档列表。
export async function listKnowledgeDocuments(knowledgeBaseId: number): Promise<KnowledgeDocumentItem[]> {
  const { data } = await api.get<{ code: number; message: string; data: { documents: KnowledgeDocumentItem[] } }>(`/knowledge-bases/${knowledgeBaseId}/documents`);
  if (data.code !== 0) throw new Error(data.message || '获取文档列表失败');
  return data.data.documents;
}

// getDocumentViewTicket 获取当前用户可访问文档的短期查看地址。
export async function getDocumentViewTicket(documentId: number): Promise<DocumentViewTicket> {
  const { data } = await api.get<{ code: number; message: string; data: DocumentViewTicket }>(`/knowledge-documents/${documentId}/view-ticket`);
  if (data.code !== 0 || !data.data?.view_url) throw new Error(data.message || '获取文档查看地址失败');
  return data.data;
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

// subscribeDocumentStatus 订阅文档状态事件，并在异常断线时有限延迟重连。
export function subscribeDocumentStatus(
  documentId: number,
  onStatus: (event: DocumentStatusEvent) => void,
  onError?: (error: Error) => void,
): DocumentStatusSubscription {
  let request: XMLHttpRequest | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  // close 终止当前请求和后续重连，避免页面卸载后继续更新状态。
  const close = () => {
    closed = true;
    request?.abort();
    request = null;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = null;
  };

  // connect 建立携带 Access Token 的 SSE 请求，并增量解析服务端事件。
  const connect = async () => {
    const token = await getAccessToken();
    if (closed) return;
    if (!token) {
      onError?.(new Error('登录状态已失效'));
      return;
    }
    let offset = 0;
    let buffer = '';
    request = new XMLHttpRequest();
    request.open('GET', `${API_BASE_URL}/knowledge-documents/${documentId}/events`);
    request.setRequestHeader('Accept', 'text/event-stream');
    request.setRequestHeader('Authorization', `Bearer ${token}`);

    // SSE 数据可能跨网络分片，先累积到空行边界再解析完整事件。
    request.onprogress = () => {
      if (!request) return;
      buffer += request.responseText.slice(offset);
      offset = request.responseText.length;
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() || '';
      frames.forEach((frame) => {
        const eventName = frame.split(/\r?\n/).find((line) => line.startsWith('event:'))?.slice(6).trim();
        const data = frame.split(/\r?\n/).filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim()).join('\n');
        if (eventName !== 'document.status' || !data) return;
        try {
          const event = JSON.parse(data) as DocumentStatusEvent;
          onStatus(event);
          if ([3, 4, 6].includes(event.status)) close();
        } catch {
          onError?.(new Error('文档状态事件格式错误'));
        }
      });
    };
    request.onerror = () => {
      if (!closed) onError?.(new Error('文档状态连接已断开'));
    };
    request.onloadend = () => {
      request = null;
      if (!closed) reconnectTimer = setTimeout(() => void connect(), 2000);
    };
    request.send();
  };

  void connect();
  return { close };
}
