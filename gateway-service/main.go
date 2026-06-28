package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/lijunsheng/familyos/gateway-service/config"
	"github.com/lijunsheng/familyos/gateway-service/internal/handler"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func main() {
	// 1. 加载配置
	cfg, err := config.Load("")
	if err != nil {
		log.Fatalf("加载配置失败: %v", err)
	}

	// 2. 连接 gRPC 后端
	conn, err := grpc.NewClient(cfg.GRPC.Target,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		log.Fatalf("连接 gRPC 服务失败: %v", err)
	}
	defer conn.Close()
	log.Printf("已连接到 gRPC 服务: %s", cfg.GRPC.Target)

	// 3. 创建 Gin 引擎
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()

	// 全局中间件
	r.Use(gin.Logger())
	r.Use(gin.Recovery())

	// 4. 注册路由
	authHandler := handler.NewAuthHandler(conn)

	api := r.Group("/api/v1")
	{
		auth := api.Group("/auth")
		{
			auth.POST("/register", authHandler.Register)
			auth.POST("/login", authHandler.Login)
		}
	}

	// 健康检查
	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	// 5. 启动 HTTP 服务
	addr := fmt.Sprintf(":%d", cfg.Server.HTTPPort)
	srv := &http.Server{
		Addr:    addr,
		Handler: r,
	}

	log.Printf("HTTP 网关启动在 %s (Gin)", addr)

	// 6. 优雅退出
	go func() {
		quit := make(chan os.Signal, 1)
		signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
		<-quit
		log.Println("正在关闭网关...")

		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		srv.Shutdown(ctx)
		conn.Close()
	}()

	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("HTTP 服务异常退出: %v", err)
	}
}
