package config

import (
	"fmt"

	"github.com/spf13/viper"
)

// Config 应用配置
type Config struct {
	Server   ServerConfig   `mapstructure:"server"`
	Database DatabaseConfig `mapstructure:"database"`
	JWT      JWTConfig      `mapstructure:"jwt"`
}

// ServerConfig gRPC 服务配置
type ServerConfig struct {
	GRPCPort int `mapstructure:"grpc_port"`
}

// DatabaseConfig 数据库配置
type DatabaseConfig struct {
	DSN string `mapstructure:"dsn"`
}

// JWTConfig JWT 配置
type JWTConfig struct {
	Secret string `mapstructure:"secret"`
}

// Load 使用 Viper 从配置文件加载配置
func Load(configPath string) (*Config, error) {
	v := viper.New()

	// 配置文件名称
	v.SetConfigName("config")
	// 配置文件类型
	v.SetConfigType("yaml")
	// 配置文件搜索路径
	v.AddConfigPath(".")
	v.AddConfigPath("./config")
	v.AddConfigPath("../config")
	if configPath != "" {
		v.AddConfigPath(configPath)
	}

	// 也支持从环境变量覆盖：DATABASE_DSN → database.dsn
	v.SetEnvPrefix("FAMILYOS")
	v.AutomaticEnv()

	// 设置默认值
	v.SetDefault("server.grpc_port", 50051)

	// 读取配置文件
	if err := v.ReadInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, fmt.Errorf("读取配置文件失败: %w", err)
		}
		// 配置文件不存在时继续，使用默认值 + 环境变量
	}

	// 解析到结构体
	var cfg Config
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("解析配置失败: %w", err)
	}

	// 校验必填项
	if cfg.Database.DSN == "" {
		return nil, fmt.Errorf("database.dsn 未配置")
	}
	if cfg.JWT.Secret == "" {
		return nil, fmt.Errorf("jwt.secret 未配置")
	}

	return &cfg, nil
}
