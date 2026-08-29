package server

import (
	"context"
	"testing"
	"time"

	knowledgev1 "github.com/lijunsheng/familyos/proto/gen/knowledge/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

// TestKnowledgeInternalServerRejectsInvalidToken 验证内部下载接口不会接受缺失或错误的服务令牌。
func TestKnowledgeInternalServerRejectsInvalidToken(t *testing.T) {
	server := NewKnowledgeInternalServer(nil, "expected-token", time.Minute)
	contexts := []context.Context{
		context.Background(),
		metadata.NewIncomingContext(context.Background(), metadata.Pairs(internalTokenHeader, "wrong-token")),
	}
	for _, ctx := range contexts {
		_, err := server.GetDocumentDownloadTicket(ctx, &knowledgev1.GetDocumentDownloadTicketRequest{DocumentId: 1, IndexVersion: 1})
		if status.Code(err) != codes.Unauthenticated {
			t.Fatalf("错误码 = %v，期望 %v", status.Code(err), codes.Unauthenticated)
		}
	}
}

// TestKnowledgeInternalServerRejectsInvalidRequest 验证通过鉴权后仍会拒绝非法文档参数。
func TestKnowledgeInternalServerRejectsInvalidRequest(t *testing.T) {
	server := NewKnowledgeInternalServer(nil, "expected-token", time.Minute)
	ctx := metadata.NewIncomingContext(context.Background(), metadata.Pairs(internalTokenHeader, "expected-token"))
	response, err := server.GetDocumentDownloadTicket(ctx, &knowledgev1.GetDocumentDownloadTicketRequest{DocumentId: -1, IndexVersion: 1})
	if err != nil || response.GetCode() != 4001 {
		t.Fatalf("response=%+v err=%v", response, err)
	}
}
