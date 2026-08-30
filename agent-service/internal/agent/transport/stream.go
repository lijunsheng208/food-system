package transport

import "github.com/lijunsheng/familyos/agent-service/internal/agent/citation"

// StreamEvent 描述 Agent 向 gRPC 层输出的增量事件。
type StreamEvent struct {
	Type     string
	Content  string
	Citation *citation.Citation
}

// Emitter 将 Graph 事件发送到具体传输层，并通过错误传播客户端取消。
type Emitter func(StreamEvent) error
