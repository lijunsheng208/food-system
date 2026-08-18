package handler

import (
	"net/http"
	"testing"
)

// TestFamilyHTTPStatus 验证家庭业务码能够稳定映射为对应的 HTTP 状态码。
func TestFamilyHTTPStatus(t *testing.T) {
	tests := []struct {
		name string
		code int32
		want int
	}{
		{name: "success", code: 0, want: http.StatusOK},
		{name: "user not found", code: 1004, want: http.StatusNotFound},
		{name: "family not found", code: 2001, want: http.StatusNotFound},
		{name: "member not found", code: 2009, want: http.StatusNotFound},
		{name: "meal plan not found", code: 2107, want: http.StatusNotFound},
		{name: "already in family", code: 2002, want: http.StatusConflict},
		{name: "family full", code: 2006, want: http.StatusConflict},
		{name: "not in family", code: 2003, want: http.StatusForbidden},
		{name: "no permission", code: 2004, want: http.StatusForbidden},
		{name: "cannot operate owner", code: 2007, want: http.StatusForbidden},
		{name: "invalid invite code", code: 2005, want: http.StatusBadRequest},
		{name: "invalid meal date", code: 2101, want: http.StatusBadRequest},
		{name: "internal error", code: 1999, want: http.StatusInternalServerError},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := familyHTTPStatus(tt.code); got != tt.want {
				t.Fatalf("familyHTTPStatus(%d) = %d, want %d", tt.code, got, tt.want)
			}
		})
	}
}
