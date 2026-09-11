// agent-index-event-adapter 将 RocketMQ 文档事件可靠转发到 Python Agent。
package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	rocketmq "github.com/apache/rocketmq-clients/golang/v5"
	v2 "github.com/apache/rocketmq-clients/golang/v5/protocol/v2"
	agentv1 "github.com/lijunsheng/familyos/proto/gen/agent/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

const tokenHeader = "x-familyos-internal-token"

// main 启动 RocketMQ Consumer 和 Python gRPC 转发客户端。
func main() {
	endpoint := env("FAMILYOS_ADAPTER_ROCKETMQ_ENDPOINT", "127.0.0.1:8083")
	group := env("FAMILYOS_ADAPTER_CONSUMER_GROUP", "familyos-agent-document-indexer")
	topic := env("FAMILYOS_ADAPTER_TOPIC", "familyos-rag-document")
	target := env("FAMILYOS_ADAPTER_PYTHON_TARGET", "127.0.0.1:50053")
	token := os.Getenv("FAMILYOS_ADAPTER_INTERNAL_TOKEN")
	if token == "" {
		log.Fatal("FAMILYOS_ADAPTER_INTERNAL_TOKEN 必须配置")
	}

	conn, err := grpc.NewClient(target, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("连接 Python Ingress 失败: %v", err)
	}
	defer conn.Close()
	client := agentv1.NewDocumentIndexIngressServiceClient(conn)

	cfg := &rocketmq.Config{Endpoint: endpoint, ConsumerGroup: group}
	consumer, err := rocketmq.NewSimpleConsumer(cfg, rocketmq.WithSimpleAwaitDuration(5*time.Second), rocketmq.WithSimpleSubscriptionExpressions(map[string]*rocketmq.FilterExpression{topic: rocketmq.NewFilterExpression("INDEX")}))
	if err != nil {
		log.Fatalf("初始化 RocketMQ Consumer 失败: %v", err)
	}
	if err := consumer.Start(); err != nil {
		log.Fatalf("启动 RocketMQ Consumer 失败: %v", err)
	}
	defer consumer.GracefulStop()

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	for ctx.Err() == nil {
		messages, receiveErr := consumer.Receive(ctx, 16, 60*time.Second)
		if receiveErr != nil {
			if ctx.Err() != nil || isMessageNotFound(receiveErr) {
				continue
			}
			log.Printf("接收 RocketMQ 消息失败: %v", receiveErr)
			continue
		}
		for _, message := range messages {
			if err := forward(ctx, client, token, message.GetBody()); err != nil {
				if status.Code(err) == 3 {
					log.Printf("丢弃非法文档事件: %v", err)
				} else {
					log.Printf("转发 Python 失败，等待 RocketMQ 重投: %v", err)
					continue
				}
			}
			if err := consumer.Ack(ctx, message); err != nil {
				log.Printf("确认 RocketMQ 消息失败: %v", err)
			}
		}
	}
}

// forward 将事件原文提交给 Python，确保由 Python 完成最终契约校验和幂等落库。
func forward(ctx context.Context, client agentv1.DocumentIndexIngressServiceClient, token string, body []byte) error {
	requestCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	requestCtx = metadata.AppendToOutgoingContext(requestCtx, tokenHeader, token)
	_, err := client.AcceptDocumentIndexEvent(requestCtx, &agentv1.AcceptDocumentIndexEventRequest{EventPayload: body})
	return err
}

// isMessageNotFound 判断 RocketMQ 长轮询无消息返回，避免制造错误日志。
func isMessageNotFound(err error) bool {
	rpcErr, ok := rocketmq.AsErrRpcStatus(err)
	return ok && rpcErr.GetCode() == int32(v2.Code_MESSAGE_NOT_FOUND)
}

// env 读取环境变量并为本地开发提供非敏感默认值。
func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
