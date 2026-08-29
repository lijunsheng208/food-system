package provider

import (
	"context"
	"errors"
	"fmt"
	rocketmq "github.com/apache/rocketmq-clients/golang/v5"
	"github.com/apache/rocketmq-clients/golang/v5/credentials"
	v2 "github.com/apache/rocketmq-clients/golang/v5/protocol/v2"
	"github.com/lijunsheng/familyos/agent-service/internal/service"
	"log"
	"time"
)

// RocketMQDocumentConsumer 使用 RocketMQ 5.x SimpleConsumer 接收 INDEX 消息。
type RocketMQDocumentConsumer struct {
	consumer  rocketmq.SimpleConsumer
	receiver  *service.DocumentIndexReceiver
	batch     int32
	invisible time.Duration
}

// NewRocketMQDocumentConsumer 创建并启动文档 Consumer。
func NewRocketMQDocumentConsumer(endpoint, accessKey, accessSecret, group, topic string, batch int32, invisible time.Duration, receiver *service.DocumentIndexReceiver) (*RocketMQDocumentConsumer, error) {
	if receiver == nil {
		return nil, fmt.Errorf("文档索引接收器不能为空")
	}
	cfg := &rocketmq.Config{Endpoint: endpoint, ConsumerGroup: group}
	if accessKey != "" {
		cfg.Credentials = &credentials.SessionCredentials{AccessKey: accessKey, AccessSecret: accessSecret}
	}
	c, err := rocketmq.NewSimpleConsumer(cfg, rocketmq.WithSimpleAwaitDuration(5*time.Second), rocketmq.WithSimpleSubscriptionExpressions(map[string]*rocketmq.FilterExpression{topic: rocketmq.NewFilterExpression("INDEX")}))
	if err != nil {
		return nil, err
	}
	if err = c.Start(); err != nil {
		return nil, err
	}
	return &RocketMQDocumentConsumer{consumer: c, receiver: receiver, batch: batch, invisible: invisible}, nil
}

// Run 持续接收、落库并确认消息。
func (c *RocketMQDocumentConsumer) Run(ctx context.Context) {
	for ctx.Err() == nil {
		msgs, err := c.consumer.Receive(ctx, c.batch, c.invisible)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			// 长轮询没有新消息属于正常空闲状态，不记录为消费失败。
			if rpcErr, ok := rocketmq.AsErrRpcStatus(err); ok && rpcErr.GetCode() == int32(v2.Code_MESSAGE_NOT_FOUND) {
				continue
			}
			log.Printf("接收 RocketMQ 消息失败: %v", err)
			// Broker 暂时不可用时延迟重试，避免错误立即返回造成 CPU 空转和日志风暴。
			select {
			case <-ctx.Done():
				return
			case <-time.After(time.Second):
			}
			continue
		}
		for _, msg := range msgs {
			_, err := c.receiver.Receive(ctx, msg.GetBody())
			if err != nil && !errors.Is(err, service.ErrInvalidDocumentIndexEvent) {
				continue
			}
			if ackErr := c.consumer.Ack(ctx, msg); ackErr != nil {
				log.Printf("确认 RocketMQ 消息失败: %v", ackErr)
			}
		}
	}
}

// Close 优雅停止 Consumer。
func (c *RocketMQDocumentConsumer) Close() error { return c.consumer.GracefulStop() }
