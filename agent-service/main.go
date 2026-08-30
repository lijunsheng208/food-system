package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"strconv"
	"syscall"

	"github.com/lijunsheng/familyos/agent-service/config"
	"github.com/lijunsheng/familyos/agent-service/internal/provider"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/chunker"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/embedding"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/indexer"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/lexical"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/parser"
	ragrepository "github.com/lijunsheng/familyos/agent-service/internal/rag/repository"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/vectorstore"
	"github.com/lijunsheng/familyos/agent-service/internal/repository"
	"github.com/lijunsheng/familyos/agent-service/internal/service"
	"gorm.io/driver/mysql"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

// main 启动文档索引任务接收器，并在退出时停止 RocketMQ Consumer。
func main() {
	cfg, err := config.Load("")
	if err != nil {
		log.Fatalf("加载 Agent 配置失败: %v", err)
	}
	db, err := gorm.Open(mysql.Open(cfg.Database.DSN), &gorm.Config{})
	if err != nil {
		log.Fatalf("连接 Agent 数据库失败: %v", err)
	}
	taskRepo := repository.NewDocumentTaskRepo(db)
	receiver := service.NewDocumentIndexReceiver(taskRepo)
	consumer, err := provider.NewRocketMQDocumentConsumer(
		cfg.RocketMQ.Endpoint, cfg.RocketMQ.AccessKey, cfg.RocketMQ.AccessSecret,
		cfg.RocketMQ.ConsumerGroup, cfg.RocketMQ.Topic, cfg.RocketMQ.ReceiveBatchSize,
		cfg.RocketMQ.InvisibleDuration, receiver,
	)
	if err != nil {
		log.Fatalf("初始化文档消息 Consumer 失败: %v", err)
	}
	defer func() {
		if err := consumer.Close(); err != nil {
			log.Printf("关闭 RocketMQ 文档 Consumer 失败: %v", err)
		}
	}()

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	if cfg.RAG.Enabled {
		logicClient, logicErr := provider.NewLogicClient(cfg.Logic.Target, cfg.Logic.AgentToken, cfg.Logic.RequestTimeout)
		if logicErr != nil {
			log.Fatalf("初始化 Logic 内部客户端失败: %v", logicErr)
		}
		defer func() {
			if closeErr := logicClient.Close(); closeErr != nil {
				log.Printf("关闭 Logic 内部客户端失败: %v", closeErr)
			}
		}()
		vectorDB, vectorErr := gorm.Open(postgres.Open(cfg.RAG.PGVector.DSN), &gorm.Config{})
		if vectorErr != nil {
			log.Fatalf("连接 pgvector 数据库失败: %v", vectorErr)
		}
		embedder, embeddingErr := embedding.NewOpenAICompatible(embedding.OpenAICompatibleConfig{BaseURL: cfg.RAG.Embedding.BaseURL, APIKey: cfg.RAG.Embedding.APIKey, Model: cfg.RAG.Embedding.Model, DimensionsValue: cfg.RAG.Embedding.Dimensions, BatchSize: cfg.RAG.Embedding.BatchSize, Timeout: cfg.RAG.Embedding.Timeout})
		if embeddingErr != nil {
			log.Fatalf("初始化 Embedding 客户端失败: %v", embeddingErr)
		}
		store, storeErr := vectorstore.NewPGVector(vectorDB, cfg.RAG.Embedding.Dimensions)
		if storeErr != nil {
			log.Fatalf("初始化 pgvector 存储失败: %v", storeErr)
		}
		documentChunker, chunkErr := chunker.NewGeneral(chunker.GeneralConfig{Size: cfg.RAG.ChunkSize, Overlap: cfg.RAG.ChunkOverlap})
		if chunkErr != nil {
			log.Fatalf("初始化文档切片器失败: %v", chunkErr)
		}
		var lexicalStore lexical.Retriever
		if cfg.RAG.OpenSearch.Enabled {
			value, lexicalErr := lexical.NewOpenSearch(lexical.Config{Endpoint: cfg.RAG.OpenSearch.Endpoint, Username: cfg.RAG.OpenSearch.Username, Password: cfg.RAG.OpenSearch.Password, Index: cfg.RAG.OpenSearch.Index, RequestTimeout: cfg.RAG.OpenSearch.RequestTimeout})
			if lexicalErr != nil {
				log.Fatalf("初始化 OpenSearch BM25 失败: %v", lexicalErr)
			}
			lexicalStore = value
		}
		documentIndexer, indexerErr := indexer.NewDocumentIndexer(parser.NewRegistry(), documentChunker, embedder, store, ragrepository.NewChunkRepo(db), indexer.DocumentIndexerConfig{DownloadTimeout: cfg.RAG.DownloadTimeout, MaxFileSize: cfg.RAG.MaxFileSize, Lexical: lexicalStore})
		if indexerErr != nil {
			log.Fatalf("初始化文档索引器失败: %v", indexerErr)
		}
		hostname, hostErr := os.Hostname()
		if hostErr != nil {
			log.Fatalf("读取 Worker 主机名失败: %v", hostErr)
		}
		worker, workerErr := service.NewDocumentTaskWorker(taskRepo, logicClient, documentIndexer, service.DocumentTaskWorkerConfig{WorkerID: "agent-service-" + hostname + "-" + strconv.Itoa(os.Getpid()), PollInterval: cfg.Worker.PollInterval, LockTimeout: cfg.Worker.LockTimeout, RetryBase: cfg.Worker.RetryBase, RetryMax: cfg.Worker.RetryMax, MaxAttempts: cfg.Worker.MaxAttempts})
		if workerErr != nil {
			log.Fatalf("初始化文档索引 Worker 失败: %v", workerErr)
		}
		go worker.Run(ctx)
		log.Println("文档索引 Worker 已启动")
	}
	log.Printf("文档索引 Consumer 已启动: group=%s topic=%s tag=INDEX", cfg.RocketMQ.ConsumerGroup, cfg.RocketMQ.Topic)
	consumer.Run(ctx)
}
