package config

import (
	"fmt"
	"strings"

	"github.com/spf13/viper"
)

// Config 网关配置
type Config struct {
	Server ServerConfig `mapstructure:"server"`
	GRPC   GRPCConfig   `mapstructure:"grpc"`
	OSS    OSSConfig    `mapstructure:"oss"`
	JWT    JWTConfig    `mapstructure:"jwt"`
}

// ServerConfig HTTP 服务配置
type ServerConfig struct {
	HTTPPort int `mapstructure:"http_port"`
}

// OSSConfig 阿里云 OSS 配置
type OSSConfig struct {
	Endpoint        string `mapstructure:"endpoint"`
	AccessKeyID     string `mapstructure:"access_key_id"`
	AccessKeySecret string `mapstructure:"access_key_secret"`
	BucketName      string `mapstructure:"bucket_name"`
	CustomDomain    string `mapstructure:"custom_domain"`
}

// GRPCConfig gRPC 连接配置
type GRPCConfig struct {
	Target string `mapstructure:"target"`
}

type JWTConfig struct {
	Secret   string `mapstructure:"secret"`
	Issuer   string `mapstructure:"issuer"`
	Audience string `mapstructure:"audience"`
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
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	v.AutomaticEnv()
	_ = v.BindEnv("jwt.secret", "FAMILYOS_JWT_SECRET", "FAMILYOS_GW_JWT_SECRET")

	v.SetDefault("server.http_port", 8080)
	v.SetDefault("grpc.target", "localhost:50051")
	v.SetDefault("jwt.issuer", "familyos")
	v.SetDefault("jwt.audience", "familyos-mobile")

	if err := v.ReadInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, fmt.Errorf("读取配置文件失败: %w", err)
		}
	}

	var cfg Config
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("解析配置失败: %w", err)
	}
	if cfg.JWT.Secret == "" || cfg.JWT.Issuer == "" || cfg.JWT.Audience == "" {
		return nil, fmt.Errorf("jwt secret、issuer 和 audience 必须配置")
	}

	return &cfg, nil
}
