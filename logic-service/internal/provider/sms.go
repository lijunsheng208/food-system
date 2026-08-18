package provider

import (
	"context"
	"log"
)

// ConsoleSMSProvider 仅用于开发环境，将验证码输出到逻辑服务日志。
type ConsoleSMSProvider struct{}

func NewConsoleSMSProvider() *ConsoleSMSProvider {
	return &ConsoleSMSProvider{}
}

func (p *ConsoleSMSProvider) SendLoginCode(_ context.Context, phone, code string) error {
	log.Printf("[DEV SMS] 登录验证码已发送到 %s，验证码: %s", maskPhone(phone), code)
	return nil
}

func maskPhone(phone string) string {
	if len(phone) != 11 {
		return "***"
	}
	return phone[:3] + "****" + phone[7:]
}
