package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/lijunsheng/familyos/agent-service/config"
	"github.com/lijunsheng/familyos/agent-service/internal/provider"
	"github.com/lijunsheng/familyos/agent-service/internal/repository"
	"github.com/lijunsheng/familyos/agent-service/internal/service"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
)

// main 启动文档索引任务接收器，并在退出时停止 RocketMQ Consumer。
func main() {
	cfg, err := config.Load("")
	if err != nil {
		log.Fatalf("加载 Agent 配置失败: %v", err)
	}
	db, err := gorm.Open(mysql.Open(cfg.Database.DSN), &gorm.Config{})
	if err != nil {
		log.Fatalf("连接 Agent 数据库失败: %v", err)
	}
	receiver := service.NewDocumentIndexReceiver(repository.NewDocumentTaskRepo(db))
	consumer, err := provider.NewRocketMQDocumentConsumer(
		cfg.RocketMQ.Endpoint, cfg.RocketMQ.AccessKey, cfg.RocketMQ.AccessSecret,
		cfg.RocketMQ.ConsumerGroup, cfg.RocketMQ.Topic, cfg.RocketMQ.ReceiveBatchSize,
		cfg.RocketMQ.InvisibleDuration, receiver,
	)
	if err != nil {
		log.Fatalf("初始化文档消息 Consumer 失败: %v", err)
	}
	defer func() {
		if err := consumer.Close(); err != nil {
			log.Printf("关闭 RocketMQ 文档 Consumer 失败: %v", err)
		}
	}()

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	log.Printf("文档索引 Consumer 已启动: group=%s topic=%s tag=INDEX", cfg.RocketMQ.ConsumerGroup, cfg.RocketMQ.Topic)
	consumer.Run(ctx)
}
