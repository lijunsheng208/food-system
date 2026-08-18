package config

import "testing"

func TestLoadReadsSMSSecretFromEnvironment(t *testing.T) {
	t.Setenv("FAMILYOS_SMS_CODE_HMAC_SECRET", "test-sms-secret")
	cfg, err := Load("")
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.SMS.CodeHMACSecret != "test-sms-secret" {
		t.Fatalf("sms secret = %q, want environment value", cfg.SMS.CodeHMACSecret)
	}
	if cfg.Redis.Addr == "" || cfg.SMS.CodeTTL <= 0 || cfg.SMS.Cooldown <= 0 {
		t.Fatalf("invalid Redis/SMS defaults: %+v %+v", cfg.Redis, cfg.SMS)
	}
	if cfg.JWT.AccessTTL.String() != "15m0s" || cfg.JWT.RefreshTTL.String() != "720h0m0s" {
		t.Fatalf("invalid token TTL defaults: access=%v refresh=%v", cfg.JWT.AccessTTL, cfg.JWT.RefreshTTL)
	}
}
