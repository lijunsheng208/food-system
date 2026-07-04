package handler

import (
	"log"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
	"github.com/lijunsheng/familyos/pkg/oss"
)

// UploadHandler 文件上传处理器
type UploadHandler struct {
	ossClient *oss.Client
}

// NewUploadHandler 创建上传处理器
func NewUploadHandler(ossClient *oss.Client) *UploadHandler {
	return &UploadHandler{ossClient: ossClient}
}

// UploadAvatar POST /api/v1/upload/avatar
// 上传用户头像到 OSS，返回 OSS 可访问 URL
func (h *UploadHandler) UploadAvatar(c *gin.Context) {
	if h.ossClient == nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "OSS 未配置",
		})
		return
	}

	userIDStr := c.PostForm("user_id")
	userID, err := strconv.ParseUint(userIDStr, 10, 64)
	if err != nil || userID == 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请提供有效的 user_id",
		})
		return
	}

	file, header, err := c.Request.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请选择要上传的图片",
		})
		return
	}
	defer file.Close()

	// 限制文件大小 (5MB)
	if header.Size > 5*1024*1024 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "图片大小不能超过 5MB",
		})
		return
	}

	ext := oss.ExtByContentType(header.Filename)
	url, err := h.ossClient.UploadAvatar(userID, ext, file)
	if err != nil {
		log.Printf("OSS 上传失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "头像上传失败，请稍后重试",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    0,
		"message": "上传成功",
		"url":     url,
	})
}
