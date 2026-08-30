import { API_BASE_URL } from '../config';
import { getAccessToken } from './api';

export interface AgentCitation {
  citation_id: string;
  chunk_id: string;
  document_id: number;
  content: string;
}

export type AgentChatEvent =
  | { type: 'metadata'; request_id: string }
  | { type: 'answer_delta'; request_id: string; content: string }
  | { type: 'citation'; request_id: string; citation: AgentCitation }
  | { type: 'completed'; request_id: string }
  | { type: 'error'; request_id?: string; message: string };

export interface AgentChatSubscription { close: () => void }

// streamAgentChat 建立带认证的 POST SSE 请求，并按网络分片增量解析 Agent 回答事件。
export function streamAgentChat(
  params: { knowledge_base_id: number; conversation_id?: string; message: string },
  onEvent: (event: AgentChatEvent) => void,
): AgentChatSubscription {
  let request: XMLHttpRequest | null = null;
  let closed = false;
  let offset = 0;
  let buffer = '';

  // close 取消当前 HTTP 请求，服务端会沿请求上下文取消 gRPC 和模型生成。
  const close = () => {
    closed = true;
    request?.abort();
    request = null;
  };

  // connect 获取 Access Token 后创建流式请求，避免在普通持久化存储中复制凭证。
  const connect = async () => {
    const token = await getAccessToken();
    if (closed) return;
    if (!token) { onEvent({ type: 'error', message: '登录状态已失效' }); return; }
    request = new XMLHttpRequest();
    request.open('POST', `${API_BASE_URL}/agent/chat/stream`);
    request.setRequestHeader('Authorization', `Bearer ${token}`);
    request.setRequestHeader('Accept', 'text/event-stream');
    request.setRequestHeader('Content-Type', 'application/json');
    request.onprogress = () => {
      if (!request) return;
      buffer += request.responseText.slice(offset);
      offset = request.responseText.length;
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() || '';
      for (const frame of frames) {
        const eventName = frame.split(/\r?\n/).find((line) => line.startsWith('event:'))?.slice(6).trim() as AgentChatEvent['type'] | undefined;
        const rawData = frame.split(/\r?\n/).filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim()).join('\n');
        if (!eventName || !rawData) continue;
        try {
          const payload = JSON.parse(rawData) as Record<string, unknown>;
          onEvent({ type: eventName, ...payload } as AgentChatEvent);
        } catch {
          onEvent({ type: 'error', message: 'Agent 事件格式错误' });
        }
      }
    };
    request.onerror = () => { if (!closed) onEvent({ type: 'error', message: 'Agent 连接已断开' }); };
    request.onloadend = () => { request = null; };
    request.send(JSON.stringify(params));
  };

  void connect();
  return { close };
}
