package password

import (
	"golang.org/x/crypto/bcrypt"
)

const cost = bcrypt.DefaultCost // cost=10

// Hash 对明文密码做 bcrypt 哈希
func Hash(plain string) (string, error) {
	bytes, err := bcrypt.GenerateFromPassword([]byte(plain), cost)
	if err != nil {
		return "", err
	}
	return string(bytes), nil
}

// Verify 验证明文密码与哈希是否匹配
func Verify(hashedPassword, plain string) bool {
	err := bcrypt.CompareHashAndPassword([]byte(hashedPassword), []byte(plain))
	return err == nil
}
