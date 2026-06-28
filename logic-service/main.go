package main

import (
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"

	"github.com/lijunsheng/familyos/logic-service/config"
	"github.com/lijunsheng/familyos/logic-service/internal/repository"
	"github.com/lijunsheng/familyos/logic-service/internal/server"
	"github.com/lijunsheng/familyos/logic-service/internal/service"

	authv1 "github.com/lijunsheng/familyos/proto/gen/auth/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

func main() {
	// 1. 加载配置
	cfg, err := config.Load("")
	if err != nil {
		log.Fatalf("加载配置失败: %v", err)
	}

	// 2. 初始化数据库连接
	db, err := gorm.Open(mysql.Open(cfg.Database.DSN), &gorm.Config{
		Logger: logger.Default.LogMode(logger.Info),
	})
	if err != nil {
		log.Fatalf("连接数据库失败: %v", err)
	}
	log.Println("数据库连接成功")

	// 3. 依赖注入
	userRepo := repository.NewUserRepo(db)
	authSvc := service.NewAuthService(userRepo, cfg.JWT.Secret)
	authServer := server.NewAuthServer(authSvc)

	// 4. 启动 gRPC Server
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", cfg.Server.GRPCPort))
	if err != nil {
		log.Fatalf("监听端口 %d 失败: %v", cfg.Server.GRPCPort, err)
	}

	grpcServer := grpc.NewServer()
	authv1.RegisterAuthServiceServer(grpcServer, authServer)

	// 注册反射服务（方便 grpcurl 调试）
	reflection.Register(grpcServer)

	log.Printf("gRPC 服务启动在 :%d", cfg.Server.GRPCPort)

	// 5. 优雅退出
	go func() {
		quit := make(chan os.Signal, 1)
		signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
		<-quit
		log.Println("正在关闭服务...")
		grpcServer.GracefulStop()
	}()

	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("gRPC 服务异常退出: %v", err)
	}
}
