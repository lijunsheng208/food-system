package config

import (
	"fmt"
	"strings"
	"time"

	"github.com/spf13/viper"
)

// Config 描述 Agent 服务运行所需的数据库和 RocketMQ 配置。
type Config struct {
	Database DatabaseConfig `mapstructure:"database"`
	RocketMQ RocketMQConfig `mapstructure:"rocketmq"`
}

// DatabaseConfig 描述 Agent 任务表使用的 MySQL 连接。
type DatabaseConfig struct {
	DSN string `mapstructure:"dsn"`
}

// RocketMQConfig 描述文档索引事件的消费配置。
type RocketMQConfig struct {
	Endpoint          string        `mapstructure:"endpoint"`
	AccessKey         string        `mapstructure:"access_key"`
	AccessSecret      string        `mapstructure:"access_secret"`
	ConsumerGroup     string        `mapstructure:"consumer_group"`
	Topic             string        `mapstructure:"topic"`
	ReceiveBatchSize  int32         `mapstructure:"receive_batch_size"`
	InvisibleDuration time.Duration `mapstructure:"invisible_duration"`
}

// Load 从配置文件和 FAMILYOS_AGENT_ 前缀的环境变量加载 Agent 配置。
func Load(configPath string) (*Config, error) {
	v := viper.New()
	v.SetConfigName("config")
	v.SetConfigType("yaml")
	v.AddConfigPath(".")
	v.AddConfigPath("./config")
	if configPath != "" {
		v.AddConfigPath(configPath)
	}
	v.SetEnvPrefix("FAMILYOS_AGENT")
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	v.AutomaticEnv()
	v.SetDefault("rocketmq.consumer_group", "familyos-agent-document-indexer")
	v.SetDefault("rocketmq.topic", "familyos-rag-document")
	v.SetDefault("rocketmq.receive_batch_size", 16)
	v.SetDefault("rocketmq.invisible_duration", "30s")

	if err := v.ReadInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, fmt.Errorf("读取配置文件失败: %w", err)
		}
	}
	var cfg Config
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("解析配置失败: %w", err)
	}
	if cfg.Database.DSN == "" || cfg.RocketMQ.Endpoint == "" {
		return nil, fmt.Errorf("database.dsn 和 rocketmq.endpoint 必须配置")
	}
	if (cfg.RocketMQ.AccessKey == "") != (cfg.RocketMQ.AccessSecret == "") {
		return nil, fmt.Errorf("rocketmq.access_key 和 rocketmq.access_secret 必须同时配置")
	}
	if cfg.RocketMQ.ConsumerGroup == "" || cfg.RocketMQ.Topic == "" || cfg.RocketMQ.ReceiveBatchSize <= 0 || cfg.RocketMQ.InvisibleDuration < 20*time.Second {
		return nil, fmt.Errorf("rocketmq 消费配置无效")
	}
	return &cfg, nil
}
