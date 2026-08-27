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
	"github.com/lijunsheng/familyos/gateway-service/internal/middleware"
	"github.com/lijunsheng/familyos/pkg/oss"

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

	// 3. 初始化 OSS 客户端（配置为空则跳过）
	var ossClient *oss.Client
	if cfg.OSS.Endpoint != "" && cfg.OSS.AccessKeyID != "" {
		ossClient, err = oss.NewClient(oss.Config{
			Endpoint:        cfg.OSS.Endpoint,
			AccessKeyID:     cfg.OSS.AccessKeyID,
			AccessKeySecret: cfg.OSS.AccessKeySecret,
			BucketName:      cfg.OSS.BucketName,
			CustomDomain:    cfg.OSS.CustomDomain,
		})
		if err != nil {
			log.Printf("OSS 初始化失败（上传功能不可用）: %v", err)
		} else {
			log.Println("OSS 客户端初始化成功")
		}
	} else {
		log.Println("OSS 未配置，上传功能不可用")
	}

	// 4. 创建 Gin 引擎
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()

	// 全局中间件
	r.Use(gin.Logger())
	r.Use(gin.Recovery())
	r.Use(middleware.CORS())

	// 5. 注册路由
	authHandler := handler.NewAuthHandler(conn)
	dishHandler := handler.NewDishHandler(conn)
	uploadHandler := handler.NewUploadHandler(ossClient)
	familyHandler := handler.NewFamilyHandler(conn)

	api := r.Group("/api/v1")
	{
		auth := api.Group("/auth")
		{
			auth.POST("/sms/code", authHandler.SendSMSCode)
			auth.POST("/sms/login", authHandler.SMSLogin)
			auth.POST("/refresh", authHandler.RefreshToken)
			auth.POST("/logout", authHandler.Logout)
			auth.POST("/register", authHandler.Register)
			auth.POST("/login", authHandler.Login)
		}

		protected := api.Group("")
		protected.Use(middleware.Auth(cfg.JWT.Secret, cfg.JWT.Issuer, cfg.JWT.Audience))
		protectedAuth := protected.Group("/auth")
		{
			protectedAuth.GET("/profile", authHandler.GetProfile)
			protectedAuth.PUT("/profile", authHandler.UpdateProfile)
			protectedAuth.GET("/dietary-preferences", authHandler.ListDietaryPreferences)
			protectedAuth.PUT("/dietary-preferences", authHandler.ReplaceDietaryPreferences)
		}

		dish := api.Group("/dish")
		{
			dish.GET("/categories", dishHandler.ListCategories)
			dish.GET("/dishes", dishHandler.ListDishesByCategory)
			dish.GET("/search", dishHandler.SearchDishes)
			dish.GET("/:id", dishHandler.GetDishDetail)
		}

		upload := protected.Group("/upload")
		{
			upload.POST("/avatar", uploadHandler.UploadAvatar)
		}

		family := protected.Group("/family")
		{
			family.POST("/shopping-lists/generate", familyHandler.GenerateShoppingList)
			family.GET("/shopping-lists", familyHandler.ListShoppingLists)
			family.GET("/shopping-lists/:id", familyHandler.GetShoppingList)
			family.PATCH("/shopping-list-items/:id", familyHandler.UpdateShoppingItemPurchased)
			family.POST("/shopping-list-items", familyHandler.AddManualShoppingItem)
			family.DELETE("/shopping-list-items/:id", familyHandler.DeleteShoppingItem)
			family.GET("/my", familyHandler.GetMyFamily)
			family.GET("/:family_id/dietary-profile", familyHandler.GetDietaryProfile)
			family.PUT("/:family_id/dietary-profile", familyHandler.SaveDietaryProfile)
			family.POST("/meal-plans", familyHandler.CreateMealPlan)
			family.GET("/:family_id/meal-plans", familyHandler.ListMealPlans)
			family.PATCH("/meal-plans/:id", familyHandler.UpdateMealPlan)
			family.DELETE("/meal-plans/:id", familyHandler.DeleteMealPlan)
			family.POST("/meal-plans/:id/rating", familyHandler.UpsertMealPlanRating)
			family.GET("/meal-plans/:id/ratings", familyHandler.ListMealPlanRatings)
			family.POST("/create", familyHandler.CreateFamily)
			family.PUT("/:family_id", familyHandler.UpdateFamily)
			family.DELETE("/:family_id", familyHandler.DissolveFamily)
			family.POST("/join", familyHandler.JoinFamily)
			family.POST("/leave", familyHandler.LeaveFamily)
			family.GET("/:family_id/members", familyHandler.ListMembers)
			family.PUT("/:family_id/members/:member_user_id", familyHandler.UpdateMember)
			family.DELETE("/:family_id/members/:member_user_id", familyHandler.RemoveMember)
			family.POST("/:family_id/invite-code/reset", familyHandler.ResetInviteCode)
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
