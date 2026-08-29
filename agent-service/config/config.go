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
	Logic    LogicConfig    `mapstructure:"logic"`
	Worker   WorkerConfig   `mapstructure:"worker"`
	RAG      RAGConfig      `mapstructure:"rag"`
}

// RAGConfig 描述文档索引、Embedding 和 pgvector 配置。
type RAGConfig struct {
	Enabled         bool            `mapstructure:"enabled"`
	ChunkSize       int             `mapstructure:"chunk_size"`
	ChunkOverlap    int             `mapstructure:"chunk_overlap"`
	MaxFileSize     int64           `mapstructure:"max_file_size"`
	DownloadTimeout time.Duration   `mapstructure:"download_timeout"`
	Embedding       EmbeddingConfig `mapstructure:"embedding"`
	PGVector        PGVectorConfig  `mapstructure:"pgvector"`
}

// EmbeddingConfig 描述 OpenAI-compatible Embedding 服务。
type EmbeddingConfig struct {
	BaseURL    string        `mapstructure:"base_url"`
	APIKey     string        `mapstructure:"api_key"`
	Model      string        `mapstructure:"model"`
	Dimensions int           `mapstructure:"dimensions"`
	BatchSize  int           `mapstructure:"batch_size"`
	Timeout    time.Duration `mapstructure:"timeout"`
}

// PGVectorConfig 描述向量 PostgreSQL 连接。
type PGVectorConfig struct {
	DSN string `mapstructure:"dsn"`
}

// LogicConfig 描述 Agent 调用 Logic 内部接口所需的连接配置。
type LogicConfig struct {
	Target         string        `mapstructure:"target"`
	AgentToken     string        `mapstructure:"agent_token"`
	RequestTimeout time.Duration `mapstructure:"request_timeout"`
}

// WorkerConfig 描述索引任务的领取、锁恢复和失败退避策略。
type WorkerConfig struct {
	PollInterval time.Duration `mapstructure:"poll_interval"`
	LockTimeout  time.Duration `mapstructure:"lock_timeout"`
	RetryBase    time.Duration `mapstructure:"retry_base"`
	RetryMax     time.Duration `mapstructure:"retry_max"`
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
	v.SetDefault("logic.request_timeout", "10s")
	v.SetDefault("logic.target", "")
	v.SetDefault("logic.agent_token", "")
	v.SetDefault("worker.poll_interval", "1s")
	v.SetDefault("worker.lock_timeout", "5m")
	v.SetDefault("worker.retry_base", "5s")
	v.SetDefault("worker.retry_max", "5m")
	v.SetDefault("rag.enabled", false)
	v.SetDefault("rag.chunk_size", 500)
	v.SetDefault("rag.chunk_overlap", 50)
	v.SetDefault("rag.max_file_size", 20971520)
	v.SetDefault("rag.download_timeout", "30s")
	v.SetDefault("rag.embedding.base_url", "https://api.openai.com/v1")
	v.SetDefault("rag.embedding.api_key", "")
	v.SetDefault("rag.embedding.model", "")
	v.SetDefault("rag.embedding.dimensions", 0)
	v.SetDefault("rag.embedding.batch_size", 16)
	v.SetDefault("rag.embedding.timeout", "30s")
	v.SetDefault("rag.pgvector.dsn", "")

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
	if (cfg.Logic.Target == "") != (cfg.Logic.AgentToken == "") || (cfg.Logic.Target != "" && cfg.Logic.RequestTimeout <= 0) {
		return nil, fmt.Errorf("logic.target 和 logic.agent_token 必须同时配置，且 request_timeout 必须有效")
	}
	if cfg.Worker.PollInterval <= 0 || cfg.Worker.LockTimeout <= 0 || cfg.Worker.RetryBase <= 0 || cfg.Worker.RetryMax < cfg.Worker.RetryBase {
		return nil, fmt.Errorf("worker 任务配置无效")
	}
	if cfg.RAG.Enabled {
		if cfg.Logic.Target == "" || cfg.Logic.AgentToken == "" || cfg.RAG.ChunkSize <= 0 || cfg.RAG.ChunkOverlap < 0 || cfg.RAG.ChunkOverlap >= cfg.RAG.ChunkSize || cfg.RAG.MaxFileSize <= 0 || cfg.RAG.DownloadTimeout <= 0 {
			return nil, fmt.Errorf("启用 RAG 时 Logic、下载和切片配置必须有效")
		}
		if cfg.RAG.Embedding.BaseURL == "" || cfg.RAG.Embedding.APIKey == "" || cfg.RAG.Embedding.Model == "" || cfg.RAG.Embedding.Dimensions <= 0 || cfg.RAG.Embedding.Dimensions > 2000 || cfg.RAG.Embedding.BatchSize <= 0 || cfg.RAG.Embedding.Timeout <= 0 || cfg.RAG.PGVector.DSN == "" {
			return nil, fmt.Errorf("启用 RAG 时 embedding 和 pgvector 配置必须完整")
		}
	}
	return &cfg, nil
}
