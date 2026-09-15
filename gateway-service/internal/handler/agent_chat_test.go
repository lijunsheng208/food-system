package handler

import (
	"context"
	"testing"

	"google.golang.org/grpc/metadata"
)

// TestAgentContextAddsInternalToken 验证 Gateway 只通过 gRPC metadata 传递内部认证令牌。
func TestAgentContextAddsInternalToken(t *testing.T) {
	handler := &AgentChatHandler{agentToken: "internal-test-token"}
	ctx := handler.agentContext(context.Background())
	values, ok := metadata.FromOutgoingContext(ctx)
	if !ok {
		t.Fatal("Agent 请求缺少出站 metadata")
	}
	if got := values.Get(agentInternalTokenHeader); len(got) != 1 || got[0] != "internal-test-token" {
		t.Fatalf("Agent token metadata = %v, want configured token", got)
	}
}
