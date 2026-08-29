package provider

import (
	"context"
	"fmt"
	rocketmq "github.com/apache/rocketmq-clients/golang/v5"
	"github.com/apache/rocketmq-clients/golang/v5/credentials"
)

// RocketMQSender 使用 RocketMQ 5.x Proxy 发送 Outbox 事件。
type RocketMQSender struct{ producer rocketmq.Producer }

// NewRocketMQSender 创建并启动 RocketMQ Producer。
func NewRocketMQSender(endpoint, accessKey, accessSecret string, topics []string) (*RocketMQSender, error) {
	if endpoint == "" {
		return nil, fmt.Errorf("RocketMQ endpoint 未配置")
	}
	cfg := &rocketmq.Config{Endpoint: endpoint}
	if accessKey != "" || accessSecret != "" {
		cfg.Credentials = &credentials.SessionCredentials{AccessKey: accessKey, AccessSecret: accessSecret}
	}
	p, err := rocketmq.NewProducer(cfg, rocketmq.WithTopics(topics...))
	if err != nil {
		return nil, err
	}
	if err = p.Start(); err != nil {
		return nil, err
	}
	return &RocketMQSender{producer: p}, nil
}

// Send 发送带 Tag 和事件 ID 的消息。
func (s *RocketMQSender) Send(ctx context.Context, topic, tag, key string, body []byte) error {
	m := &rocketmq.Message{Topic: topic, Body: body}
	m.SetTag(tag)
	m.SetKeys(key)
	_, err := s.producer.Send(ctx, m)
	return err
}

// Close 优雅关闭 Producer。
func (s *RocketMQSender) Close() error { return s.producer.GracefulStop() }
