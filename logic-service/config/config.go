package config

import (
	"fmt"
	"strings"
	"time"

	"github.com/spf13/viper"
)

// Config 应用配置
type Config struct {
	Server   ServerConfig   `mapstructure:"server"`
	Database DatabaseConfig `mapstructure:"database"`
	JWT      JWTConfig      `mapstructure:"jwt"`
	Redis    RedisConfig    `mapstructure:"redis"`
	SMS      SMSConfig      `mapstructure:"sms"`
	OSS      OSSConfig      `mapstructure:"oss"`
	RocketMQ RocketMQConfig `mapstructure:"rocketmq"`
}
type OSSConfig struct {
	Endpoint        string `mapstructure:"endpoint"`
	AccessKeyID     string `mapstructure:"access_key_id"`
	AccessKeySecret string `mapstructure:"access_key_secret"`
	BucketName      string `mapstructure:"bucket_name"`
	DocumentPrefix  string `mapstructure:"document_prefix"`
}

// RocketMQConfig 配置 Outbox Publisher 使用的 RocketMQ 4.x NameServer 地址。
type RocketMQConfig struct {
	Endpoint     string        `mapstructure:"endpoint"`
	AccessKey    string        `mapstructure:"access_key"`
	AccessSecret string        `mapstructure:"access_secret"`
	PollInterval time.Duration `mapstructure:"poll_interval"`
	LockTimeout  time.Duration `mapstructure:"lock_timeout"`
	RetryBase    time.Duration `mapstructure:"retry_base"`
	RetryMax     time.Duration `mapstructure:"retry_max"`
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
	Secret     string        `mapstructure:"secret"`
	Issuer     string        `mapstructure:"issuer"`
	Audience   string        `mapstructure:"audience"`
	AccessTTL  time.Duration `mapstructure:"access_ttl"`
	RefreshTTL time.Duration `mapstructure:"refresh_ttl"`
}

type RedisConfig struct {
	Addr         string        `mapstructure:"addr"`
	Password     string        `mapstructure:"password"`
	DB           int           `mapstructure:"db"`
	DialTimeout  time.Duration `mapstructure:"dial_timeout"`
	ReadTimeout  time.Duration `mapstructure:"read_timeout"`
	WriteTimeout time.Duration `mapstructure:"write_timeout"`
	KeyPrefix    string        `mapstructure:"key_prefix"`
}

type SMSConfig struct {
	Provider       string        `mapstructure:"provider"`
	CodeHMACSecret string        `mapstructure:"code_hmac_secret"`
	CodeTTL        time.Duration `mapstructure:"code_ttl"`
	Cooldown       time.Duration `mapstructure:"cooldown"`
	DailyLimit     int64         `mapstructure:"daily_limit"`
	IPHourlyLimit  int64         `mapstructure:"ip_hourly_limit"`
	IPLimitWindow  time.Duration `mapstructure:"ip_limit_window"`
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
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	v.AutomaticEnv()

	// 设置默认值
	v.SetDefault("server.grpc_port", 50051)
	v.SetDefault("jwt.issuer", "familyos")
	v.SetDefault("jwt.audience", "familyos-mobile")
	v.SetDefault("jwt.access_ttl", "15m")
	v.SetDefault("jwt.refresh_ttl", "720h")
	v.SetDefault("redis.addr", "127.0.0.1:6379")
	v.SetDefault("redis.db", 0)
	v.SetDefault("redis.dial_timeout", "3s")
	v.SetDefault("redis.read_timeout", "2s")
	v.SetDefault("redis.write_timeout", "2s")
	v.SetDefault("redis.key_prefix", "familyos:auth")
	v.SetDefault("sms.provider", "console")
	v.SetDefault("sms.code_ttl", "5m")
	v.SetDefault("sms.cooldown", "60s")
	v.SetDefault("sms.daily_limit", 10)
	v.SetDefault("sms.ip_hourly_limit", 30)
	v.SetDefault("sms.ip_limit_window", "1h")
	v.SetDefault("rocketmq.poll_interval", "1s")
	v.SetDefault("rocketmq.lock_timeout", "1m")
	v.SetDefault("rocketmq.retry_base", "1s")
	v.SetDefault("rocketmq.retry_max", "5m")

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
	if cfg.JWT.Issuer == "" || cfg.JWT.Audience == "" || cfg.JWT.AccessTTL <= 0 || cfg.JWT.RefreshTTL <= 0 {
		return nil, fmt.Errorf("jwt issuer、audience 和 token TTL 必须配置且有效")
	}
	if cfg.SMS.CodeHMACSecret == "" {
		return nil, fmt.Errorf("sms.code_hmac_secret 未配置，请通过 FAMILYOS_SMS_CODE_HMAC_SECRET 注入")
	}
	if cfg.SMS.CodeTTL <= 0 || cfg.SMS.Cooldown <= 0 || cfg.SMS.DailyLimit <= 0 || cfg.SMS.IPHourlyLimit <= 0 || cfg.SMS.IPLimitWindow <= 0 {
		return nil, fmt.Errorf("sms 验证码和限流配置必须大于 0")
	}

	return &cfg, nil
}
