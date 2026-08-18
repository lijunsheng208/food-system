package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/lijunsheng/familyos/logic-service/config"
	"github.com/lijunsheng/familyos/logic-service/internal/provider"
	"github.com/lijunsheng/familyos/logic-service/internal/repository"
	"github.com/lijunsheng/familyos/logic-service/internal/server"
	"github.com/lijunsheng/familyos/logic-service/internal/service"
	"github.com/redis/go-redis/v9"

	authv1 "github.com/lijunsheng/familyos/proto/gen/auth/v1"
	dishv1 "github.com/lijunsheng/familyos/proto/gen/dish/v1"
	familyv1 "github.com/lijunsheng/familyos/proto/gen/family/v1"
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

	redisClient := redis.NewClient(&redis.Options{
		Addr:         cfg.Redis.Addr,
		Password:     cfg.Redis.Password,
		DB:           cfg.Redis.DB,
		DialTimeout:  cfg.Redis.DialTimeout,
		ReadTimeout:  cfg.Redis.ReadTimeout,
		WriteTimeout: cfg.Redis.WriteTimeout,
	})
	defer redisClient.Close()
	redisCtx, redisCancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer redisCancel()
	if err := redisClient.Ping(redisCtx).Err(); err != nil {
		log.Fatalf("连接 Redis 失败: %v", err)
	}
	log.Println("Redis 连接成功")

	// 3. 依赖注入
	userRepo := repository.NewUserRepo(db)
	familyRepo := repository.NewFamilyRepo(db)

	authSvc := service.NewAuthService(userRepo, familyRepo, cfg.JWT.Secret)
	smsStore := repository.NewSMSCodeStore(redisClient, cfg.Redis.KeyPrefix)
	sessionStore := repository.NewRefreshSessionStore(redisClient, cfg.Redis.KeyPrefix)
	authSvc.ConfigureTokens(sessionStore, service.TokenConfig{
		Issuer: cfg.JWT.Issuer, Audience: cfg.JWT.Audience,
		AccessTTL: cfg.JWT.AccessTTL, RefreshTTL: cfg.JWT.RefreshTTL,
	})
	var smsProvider service.SMSProvider
	switch cfg.SMS.Provider {
	case "console":
		smsProvider = provider.NewConsoleSMSProvider()
	default:
		log.Fatalf("不支持的短信 Provider: %s", cfg.SMS.Provider)
	}
	authSvc.ConfigureSMS(smsStore, smsProvider, service.SMSCodeConfig{
		HMACSecret:    cfg.SMS.CodeHMACSecret,
		CodeTTL:       cfg.SMS.CodeTTL,
		Cooldown:      cfg.SMS.Cooldown,
		DailyLimit:    cfg.SMS.DailyLimit,
		IPLimit:       cfg.SMS.IPHourlyLimit,
		IPLimitWindow: cfg.SMS.IPLimitWindow,
	})
	authServer := server.NewAuthServer(authSvc)

	dishRepo := repository.NewDishRepo(db)
	dishSvc := service.NewDishService(dishRepo)
	dishServer := server.NewDishServer(dishSvc)

	mealPlanRepo := repository.NewMealPlanRepo(db)
	mealPlanSvc := service.NewMealPlanService(mealPlanRepo, familyRepo, dishRepo)
	shoppingRepo := repository.NewShoppingListRepo(db)
	shoppingSvc := service.NewShoppingListService(shoppingRepo, familyRepo, mealPlanRepo, dishRepo)
	familySvc := service.NewFamilyService(familyRepo, userRepo)
	familyServer := server.NewFamilyServer(familySvc, mealPlanSvc, shoppingSvc)

	// 4. 启动 gRPC Server
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", cfg.Server.GRPCPort))
	if err != nil {
		log.Fatalf("监听端口 %d 失败: %v", cfg.Server.GRPCPort, err)
	}

	grpcServer := grpc.NewServer()
	authv1.RegisterAuthServiceServer(grpcServer, authServer)
	dishv1.RegisterDishServiceServer(grpcServer, dishServer)
	familyv1.RegisterFamilyServiceServer(grpcServer, familyServer)

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
