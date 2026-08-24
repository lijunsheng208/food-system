package service

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
)

type fakeDietaryPreferenceStore struct {
	preferences []model.UserDietaryPreference
}

// ListByUser 返回测试中最近一次保存的偏好。
func (s *fakeDietaryPreferenceStore) ListByUser(_ context.Context, userID uint64) ([]model.UserDietaryPreference, error) {
	result := make([]model.UserDietaryPreference, 0, len(s.preferences))
	for _, preference := range s.preferences {
		if preference.UserID == userID {
			result = append(result, preference)
		}
	}
	return result, nil
}

// ReplaceByUser 模拟数据库整体替换，并补齐返回所需的标识和时间。
func (s *fakeDietaryPreferenceStore) ReplaceByUser(_ context.Context, userID uint64, preferences []model.UserDietaryPreference) error {
	now := time.Date(2026, 8, 24, 12, 0, 0, 0, time.Local)
	s.preferences = make([]model.UserDietaryPreference, len(preferences))
	for index, preference := range preferences {
		preference.ID = uint64(index + 1)
		preference.UserID = userID
		preference.CreatedAt = now
		preference.UpdatedAt = now
		s.preferences[index] = preference
	}
	return nil
}

// TestReplaceDietaryPreferencesNormalizesAndReturnsSavedValues 验证整体保存会清理空白并返回持久化结果。
func TestReplaceDietaryPreferencesNormalizesAndReturnsSavedValues(t *testing.T) {
	store := &fakeDietaryPreferenceStore{}
	service := &AuthService{dietaryRepo: store}

	result, err := service.ReplaceDietaryPreferences(context.Background(), 7, []UserDietaryPreferenceInput{
		{PreferenceType: model.DietaryPreferenceTaste, PreferenceValue: "  清淡  ", Note: "  日常口味  "},
		{PreferenceType: model.DietaryPreferenceAllergy, PreferenceValue: "花生"},
	})
	if err != nil {
		t.Fatalf("ReplaceDietaryPreferences() error = %v", err)
	}
	if len(result) != 2 {
		t.Fatalf("preference count = %d, want 2", len(result))
	}
	if result[0].PreferenceValue != "清淡" || result[0].Note != "日常口味" {
		t.Fatalf("normalized preference = %#v", result[0])
	}
	if store.preferences[0].NormalizedValue != "清淡" {
		t.Fatalf("normalized value = %q, want 清淡", store.preferences[0].NormalizedValue)
	}
}

// TestReplaceDietaryPreferencesRejectsDuplicateValues 验证同类型偏好忽略大小写后不能重复。
func TestReplaceDietaryPreferencesRejectsDuplicateValues(t *testing.T) {
	service := &AuthService{dietaryRepo: &fakeDietaryPreferenceStore{}}
	_, err := service.ReplaceDietaryPreferences(context.Background(), 7, []UserDietaryPreferenceInput{
		{PreferenceType: model.DietaryPreferenceHabit, PreferenceValue: "Low Sugar"},
		{PreferenceType: model.DietaryPreferenceHabit, PreferenceValue: "low sugar"},
	})
	if !errors.Is(err, ErrDietaryPreferenceDuplicate) {
		t.Fatalf("error = %v, want ErrDietaryPreferenceDuplicate", err)
	}
}

// TestReplaceDietaryPreferencesRejectsInvalidType 验证接口拒绝未定义的偏好类型。
func TestReplaceDietaryPreferencesRejectsInvalidType(t *testing.T) {
	service := &AuthService{dietaryRepo: &fakeDietaryPreferenceStore{}}
	_, err := service.ReplaceDietaryPreferences(context.Background(), 7, []UserDietaryPreferenceInput{
		{PreferenceType: 9, PreferenceValue: "未知偏好"},
	})
	if !errors.Is(err, ErrDietaryPreferenceType) {
		t.Fatalf("error = %v, want ErrDietaryPreferenceType", err)
	}
}
