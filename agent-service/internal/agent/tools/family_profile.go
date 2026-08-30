package tools

import "context"

// FamilyProfileProvider 定义后续从 Logic 读取家庭成员、过敏原和饮食偏好的只读边界。
type FamilyProfileProvider interface {
	GetFamilyProfile(context.Context, uint64) (any, error)
}
