package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"strconv"
	"syscall"

	"github.com/cloudwego/eino-ext/components/model/openai"
	"github.com/lijunsheng/familyos/agent-service/config"
	agentgraph "github.com/lijunsheng/familyos/agent-service/internal/agent/graph"
	"github.com/lijunsheng/familyos/agent-service/internal/provider"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/chunker"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/embedding"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/indexer"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/lexical"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/parser"
	ragrepository "github.com/lijunsheng/familyos/agent-service/internal/rag/repository"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/rerank"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/search"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/vectorstore"
	"github.com/lijunsheng/familyos/agent-service/internal/repository"
	agentserver "github.com/lijunsheng/familyos/agent-service/internal/server"
	"github.com/lijunsheng/familyos/agent-service/internal/service"
	agentv1 "github.com/lijunsheng/familyos/proto/gen/agent/v1"
	"google.golang.org/grpc"
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
		if cfg.Agent.Enabled {
			var rerankerClient rerank.Reranker
			if cfg.RAG.Rerank.Enabled {
				value, rerankErr := rerank.NewHTTP(rerank.HTTPConfig{BaseURL: cfg.RAG.Rerank.BaseURL, APIKey: cfg.RAG.Rerank.APIKey, Model: cfg.RAG.Rerank.Model, Timeout: cfg.RAG.Rerank.Timeout, TopK: cfg.Agent.TopK})
				if rerankErr != nil {
					log.Fatalf("初始化 Cross-Encoder 重排器失败: %v", rerankErr)
				}
				rerankerClient = value
			}
			hybrid, hybridErr := search.NewHybridRetriever(embedder, store, lexicalStore, search.HybridConfig{DenseWeight: cfg.RAG.OpenSearch.DenseWeight, LexicalWeight: cfg.RAG.OpenSearch.LexicalWeight, Constant: cfg.RAG.OpenSearch.RRFConstant, CandidateK: cfg.RAG.OpenSearch.CandidateK, Reranker: rerankerClient})
			if hybridErr != nil {
				log.Fatalf("初始化混合检索器失败: %v", hybridErr)
			}
			rewriteMaxTokens := cfg.Agent.Rewrite.MaxTokens
			rewriteModel, modelErr := openai.NewChatModel(ctx, &openai.ChatModelConfig{BaseURL: cfg.Agent.Rewrite.BaseURL, APIKey: cfg.Agent.Rewrite.APIKey, Model: cfg.Agent.Rewrite.Model, Timeout: cfg.Agent.Rewrite.Timeout, MaxTokens: &rewriteMaxTokens})
			if modelErr != nil {
				log.Fatalf("初始化 Query Rewrite ChatModel 失败: %v", modelErr)
			}
			chatMaxTokens := cfg.Agent.Chat.MaxTokens
			chatModel, modelErr := openai.NewChatModel(ctx, &openai.ChatModelConfig{BaseURL: cfg.Agent.Chat.BaseURL, APIKey: cfg.Agent.Chat.APIKey, Model: cfg.Agent.Chat.Model, Timeout: cfg.Agent.Chat.Timeout, MaxTokens: &chatMaxTokens})
			if modelErr != nil {
				log.Fatalf("初始化 ReAct ChatModel 失败: %v", modelErr)
			}
			chatService, chatErr := agentgraph.NewChatGraph(rewriteModel, chatModel, hybrid, agentgraph.Config{MaxSteps: cfg.Agent.MaxSteps, TopK: cfg.Agent.TopK})
			if chatErr != nil {
				log.Fatalf("初始化 ReAct 问答服务失败: %v", chatErr)
			}
			chatServer, serverErr := agentserver.NewChatServer(chatService, repository.NewConversationRepo(db), cfg.Agent.RecentMessages)
			if serverErr != nil {
				log.Fatalf("初始化 Agent gRPC 服务失败: %v", serverErr)
			}
			listener, listenErr := net.Listen("tcp", fmt.Sprintf(":%d", cfg.Agent.GRPCPort))
			if listenErr != nil {
				log.Fatalf("监听 Agent gRPC 端口失败: %v", listenErr)
			}
			grpcServer := grpc.NewServer()
			agentv1.RegisterAgentChatServiceServer(grpcServer, chatServer)
			go func() {
				<-ctx.Done()
				grpcServer.GracefulStop()
			}()
			go func() {
				if serveErr := grpcServer.Serve(listener); serveErr != nil {
					log.Printf("Agent gRPC 服务退出: %v", serveErr)
				}
			}()
			log.Printf("Eino ReAct 问答 gRPC 已启动: port=%d", cfg.Agent.GRPCPort)
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
