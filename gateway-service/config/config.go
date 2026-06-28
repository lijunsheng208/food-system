package config

import (
	"fmt"

	"github.com/spf13/viper"
)

// Config 网关配置
type Config struct {
	Server   ServerConfig `mapstructure:"server"`
	GRPC     GRPCConfig   `mapstructure:"grpc"`
}

// ServerConfig HTTP 服务配置
type ServerConfig struct {
	HTTPPort int `mapstructure:"http_port"`
}

// GRPCConfig gRPC 连接配置
type GRPCConfig struct {
	Target string `mapstructure:"target"`
}

// Load 使用 Viper 加载配置
func Load(configPath string) (*Config, error) {
	v := viper.New()

	v.SetConfigName("config")
	v.SetConfigType("yaml")
	v.AddConfigPath(".")
	v.AddConfigPath("./config")
	v.AddConfigPath("../config")
	if configPath != "" {
		v.AddConfigPath(configPath)
	}

	v.SetEnvPrefix("FAMILYOS_GW")
	v.AutomaticEnv()

	v.SetDefault("server.http_port", 8080)
	v.SetDefault("grpc.target", "localhost:50051")

	if err := v.ReadInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, fmt.Errorf("读取配置文件失败: %w", err)
		}
	}

	var cfg Config
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("解析配置失败: %w", err)
	}

	return &cfg, nil
}
