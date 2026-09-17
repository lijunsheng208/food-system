# FamilyOS

FamilyOS 是一个面向家庭场景的饮食与知识管理应用，覆盖用户认证、菜谱浏览、家庭菜单、购物清单、饮食偏好，以及基于个人或家庭文档的 AI 问答。

项目使用 Expo/React Native 构建移动端，以 Go 实现 HTTP Gateway、核心业务服务和消息适配器，以 Python、LangGraph 和 Milvus 实现文档索引与 Agent 问答。服务之间通过 gRPC 和 RocketMQ 协作。

> 当前仓库主要用于开发、联调和检索效果评估。生产部署前必须替换示例密钥，启用基础设施鉴权与 TLS，并补充正式的迁移、监控、备份和容灾方案。

## 功能概览

- 用户名密码登录、短信验证码登录、Access/Refresh Token 轮换
- 个人资料、饮食偏好和头像管理
- 菜谱分类、关键词搜索、菜谱详情和烹饪步骤计时
- 家庭创建、加入、成员管理和邀请口令
- 家庭菜单、菜单评价、饮食档案和购物清单
- 个人或家庭知识库文档上传、异步索引和状态追踪
- 基于 LangGraph 的流式多轮问答、Tool Calling 和文档引用
- Milvus Dense/Sparse 混合检索、可选父子块重排和 OpenSearch BM25
- 可选 Neo4j Graph RAG；不可用时回退到常规混合检索

## 系统架构

```text
移动端 / curl / Postman
          │ HTTP JSON :8080
          ▼
Gateway Service（Gin）
          │
          ├── gRPC ──► Logic Service :50051
          │                 ├── MySQL（用户、家庭、菜单、知识库元数据）
          │                 ├── Redis（验证码、Refresh Session）
          │                 ├── OSS（文档和头像上传必需）
          │                 └── RocketMQ（文档索引事件）
          │
          └── gRPC ──► Python Agent Chat :50054
                            ├── MySQL（任务、会话、Chunk、Checkpoint）
                            ├── Milvus（Dense/Sparse 向量检索）
                            ├── OpenSearch（BM25，可选）
                            ├── Neo4j（Graph RAG，可选）
                            └── OpenAI-compatible Chat API

RocketMQ Proxy :8083
          │
          ▼
Go Index Event Adapter ── gRPC :50053 ──► Python Agent Index Ingress
```

Gateway 是客户端唯一需要访问的 HTTP 入口。Logic、Python Agent Chat 和 Index Ingress 都是内部 gRPC 服务，不应直接暴露到公网。

文档上传后的索引链路为：Logic 将 Outbox 事件发布到 RocketMQ，Go Adapter 消费事件并转发给 Python Agent，Python Worker 完成解析、父子切块、BGE-M3 向量化和索引写入，成功后再通知 Logic 激活对应文档版本。

## 技术栈

- 核心后端：Go、Gin、gRPC、GORM、MySQL、Redis
- Agent：Python 3.10+、LangGraph、LangChain、gRPC、OpenTelemetry、Prometheus
- 检索：BGE-M3、Milvus、可选 OpenSearch、可选 Cross-Encoder Reranker
- Graph RAG：Neo4j、受控检索路由和原文 Chunk 回查
- 消息与存储：RocketMQ、阿里云 OSS（启用文档或头像上传时必需）
- 移动端：Expo SDK 56、React Native、TypeScript、React Navigation
- 协议：Protocol Buffers，源文件位于 [`proto/`](proto/)

## 仓库结构

```text
.
├── gateway-service/             # HTTP 网关、JWT 鉴权和 SSE 转发
├── logic-service/               # 用户、家庭、菜谱、菜单和知识库业务服务
├── agent-python-service/        # 当前文档索引、混合检索和 LangGraph Agent
├── agent-index-event-adapter/   # RocketMQ 5 消费与 Python gRPC 转发
├── agent-service/               # 迁移前的 Go Agent，仅用于历史对照
├── mobile-app/                  # Expo/React Native 移动端
├── proto/                       # gRPC/Protobuf 定义与 Go 生成代码
├── sql/                         # 业务和 Agent 增量迁移
├── docs/                        # 设计、开发计划和验收记录
├── opensearch/                  # OpenSearch IK Analyzer 镜像与词典
├── rocketmq/                    # RocketMQ Broker/Proxy 配置
├── ops/                         # 可观测性配置
├── docker-compose.infrastructure.yml
├── 接口文档.md                  # HTTP API 说明
└── Makefile                     # 常用开发命令
```

`agent-service/` 使用 pgvector 和旧 Go Agent 链路，不属于本 README 的快速开始范围。当前默认开发链路是 `agent-python-service/` + Milvus；不要让旧 Go Agent 与 `agent-index-event-adapter` 使用同一个 RocketMQ Consumer Group，否则消息会被两个消费者分流。

## 环境要求

- Go `1.26.4` 或与 `go.mod` 兼容的版本
- Python `3.10` 或更高版本
- Node.js 与 npm
- Docker Desktop，或 Docker Engine + Compose v2
- Protocol Buffers Compiler `protoc`（仅重新生成 gRPC 代码时需要）
- MySQL 8.x：Logic 业务库和 Agent 数据库
- Redis 6.x 或更高版本
- 本地 BGE-M3 模型；默认配置路径为 `agent-python-service/models/bge-m3`
- 可访问的 OpenAI-compatible Chat API
- 文档解析按需安装 LibreOffice、OCR 和 PDF 系统依赖

## 快速开始

### 1. 获取代码并安装依赖

```bash
git clone https://github.com/lijunsheng/familyos.git
cd familyos

go mod download

python3 -m venv agent-python-service/.venv
source agent-python-service/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e agent-python-service
python -m nltk.downloader punkt_tab averaged_perceptron_tagger_eng

cd mobile-app
npm install
cd ..
```

Python Agent 默认使用本地 BGE-M3。请将模型下载或挂载到 `agent-python-service/models/bge-m3`，也可以在 Agent 配置中把 `rag.embedding.model_name` 改为实际路径。默认向量维度为 `1024`，必须与模型输出和 Milvus Collection 一致。

### 2. 启动基础设施

```bash
docker compose -f docker-compose.infrastructure.yml up -d
docker compose -f docker-compose.infrastructure.yml ps
```

上述命令会启动 Milvus（含 etcd 和 MinIO）、OpenSearch、Neo4j、RocketMQ，以及旧 Go Agent 使用的 pgvector。只运行当前 Python Agent 主链路时，可以改用最小启动命令，Compose 会自动带起所需依赖：

```bash
docker compose -f docker-compose.infrastructure.yml up -d milvus proxy
```

当前完整文档索引链路必需 Milvus 和 RocketMQ，其中 Python Agent 直接连接 Milvus，Logic 和 Adapter 连接 RocketMQ；OpenSearch、Neo4j 可通过 Agent 配置关闭，pgvector 不在当前默认链路中。

MySQL 和 Redis 不在 Compose 文件中，需要单独启动。至少需要准备：

- `familyos_logic`：Logic Service 业务数据
- `familyos_agent`：Agent 索引任务、会话、Chunk 和 LangGraph Checkpoint

### 3. 初始化数据库

根目录 `sql/` 保存增量迁移，不包含完整的基础业务 Schema。部分同日脚本存在明确的先后依赖，部分 `alter` 脚本只用于从旧版本升级，因此不要在未知数据库状态下直接按文件名批量执行全部 SQL。

> 已知限制：仓库当前没有从空库创建全部基础表的 baseline migration。全新环境需要先从项目维护者处取得基础 Schema 或可用数据库快照；仅执行仓库现有增量脚本无法完成首次初始化。

请先准备项目基础表，再按当前数据库版本审核并执行 `sql/` 中需要的迁移。Python Agent 还需要以下迁移：

```bash
mysql --default-character-set=utf8mb4 -uYOUR_USER -p familyos_agent \
  < agent-python-service/migrations/001_parent_child_chunks.sql

mysql --default-character-set=utf8mb4 -uYOUR_USER -p familyos_agent \
  < agent-python-service/migrations/002_agent_graph_checkpoint.sql
```

`sql/20260830_create_pgvector_document_vectors.sql` 只服务于旧 pgvector 链路，不需要为当前 Python Agent + Milvus 链路执行。生产环境应使用正式迁移工具记录版本，避免重复运行不可重复迁移。

### 4. 配置服务

复制当前主链路的示例配置：

```bash
cp logic-service/config/config.yaml.example logic-service/config/config.yaml
cp gateway-service/config/config.yaml.example gateway-service/config/config.yaml
cp agent-python-service/config/config.yaml.example agent-python-service/config/config.yaml
```

根据本地环境修改三个 `config.yaml`。真实配置已被 `.gitignore` 忽略，密钥也可以通过环境变量注入；通用变量和 Adapter 变量命名可参考 [`.env.example`](.env.example)。其中仍保留旧 Go Agent 的兼容项，当前 Python Agent 的参数和默认值以 [`agent-python-service/config/config.yaml.example`](agent-python-service/config/config.yaml.example) 为准，不要未经核对就整体加载 `.env.example`。不要提交真实数据库密码、Token 或第三方 API Key。

以下配置必须成对一致：

| 用途 | 一端 | 另一端 |
| --- | --- | --- |
| JWT 签发与验签 | Logic `jwt.secret` | Gateway `jwt.secret` |
| Logic 内部接口 | Python `logic.agent_token` | Logic `internal.agent_token` |
| 索引事件转发 | Adapter `FAMILYOS_ADAPTER_INTERNAL_TOKEN` | Python `ingress.token` |
| Agent Chat | Gateway `agent.token` | Python `chat.token` |

还需要重点检查：

- Logic：MySQL、Redis、短信 HMAC 密钥；启用文档知识库时还必须配置 OSS、RocketMQ Proxy `127.0.0.1:8083` 和内部 Token
- Gateway：Logic `localhost:50051`、Python Agent `127.0.0.1:50054`、JWT 和 Agent Chat Token
- Python Agent：Agent MySQL、Logic 地址、Milvus、本地 BGE-M3、Chat 模型和两个 gRPC Token
- 可选能力：OpenSearch、Reranker、Query Rewrite、Neo4j Graph RAG 和 OpenTelemetry

Logic 和 Adapter 都使用 RocketMQ 5 gRPC 客户端连接 Proxy `127.0.0.1:8083`。`localhost:9876` 是 NameServer 地址，只供 Broker、Proxy 和管理命令使用，不应配置为这两个应用进程的客户端端点。OSS 对用户、菜谱和家庭等核心接口可选，但文档知识库和上传能力依赖 OSS；仓库暂未提供本地文件存储替代实现。

### 5. 启动后端

完整链路建议按以下顺序在四个终端中启动。每个终端都从仓库根目录开始；Logic、Gateway 和 Python Agent 读取上一步创建的配置文件，Adapter 需要显式提供与 Python `ingress.token` 相同的 Token：

```bash
# 终端一：核心业务 gRPC
make run-logic

# 终端二：Python 索引 Worker、Index Ingress 和 Agent Chat
source agent-python-service/.venv/bin/activate
(cd agent-python-service && python -m familyos_agent --config config/config.yaml)

# 终端三：RocketMQ -> Python Agent 事件适配器
FAMILYOS_ADAPTER_INTERNAL_TOKEN="replace-with-the-ingress-token" \
  make run-index-event-adapter

# 终端四：HTTP Gateway
make run-gateway
```

如果只调试用户、菜谱或家庭等核心业务，可以只启动 Logic 和 Gateway；文档索引与 AI 问答需要完整链路。

默认端口如下：

| 服务 | 地址 | 用途 |
| --- | --- | --- |
| Gateway | `http://localhost:8080` | 客户端 HTTP API |
| Logic | `localhost:50051` | 核心业务 gRPC |
| Python Agent Ingress | `localhost:50053` | Adapter 内部索引事件入口 |
| Python Agent Chat | `localhost:50054` | 流式问答 gRPC |
| Agent Metrics | `http://localhost:9108/metrics` | Prometheus 指标 |
| Milvus | `localhost:19530` | Dense/Sparse 向量检索 |
| OpenSearch | `http://localhost:9200` | 可选 BM25 检索 |
| Neo4j | `http://localhost:7474` / `localhost:7687` | 可选管理界面 / Bolt |
| RocketMQ NameServer | `localhost:9876` | NameServer |
| RocketMQ Proxy | `localhost:8083` | RocketMQ 5 客户端入口 |

验证 Gateway：

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

### 6. 启动移动端

```bash
cd mobile-app
npm start
```

也可以直接运行：

```bash
npm run android
npm run ios
npm run web
```

开发环境 API 地址在 [`mobile-app/src/config.ts`](mobile-app/src/config.ts) 中配置。真机调试时将 `DEV_HOST` 设置为电脑的局域网 IP；Android 模拟器通常使用 `10.0.2.2`，iOS 模拟器通常使用 `localhost`。修改后需要重新启动 Expo。

## API 文档

完整接口、请求示例、认证约定和业务状态码见 [`接口文档.md`](接口文档.md)。常用入口：

- `GET /health`：Gateway 健康检查
- `POST /api/v1/auth/register`：用户注册
- `POST /api/v1/auth/login`：密码登录
- `POST /api/v1/auth/sms/login`：短信验证码登录或自动注册
- `GET /api/v1/dish/categories`：菜谱分类
- `GET /api/v1/dish/search`：菜谱搜索
- `GET /api/v1/family/my`：当前用户家庭
- `POST /api/v1/agent/conversations`：创建 Agent 会话
- `POST /api/v1/agent/chat/stream`：流式 AI 问答

内部 gRPC 契约位于 [`proto/`](proto/)，Go 生成代码位于 [`proto/gen/`](proto/gen/)。Python Agent 的生成代码位于 `agent-python-service/src/familyos_agent/generated/`。

## 开发与验证

常用命令：

```bash
make install-deps             # 整理 Go 依赖并安装 protoc 插件
make proto-gen                # 重新生成 Go gRPC 代码
mkdir -p deploy               # 首次构建前创建输出目录
make build-logic              # 构建 Logic Service
make build-gateway            # 构建 Gateway Service
make run-index-event-adapter  # 启动索引事件适配器
```

运行受影响模块的检查：

```bash
go test ./...

cd agent-python-service
source .venv/bin/activate
python -m unittest discover -s tests/unit -p 'test_*.py'

cd ../mobile-app
npx tsc --noEmit
```

Python 集成测试和检索评估需要相应的 MySQL、Milvus、模型与数据集；详细说明见 [`agent-python-service/README.md`](agent-python-service/README.md) 及各评估目录下的 README。Go 的 Redis 集成测试在缺少 `FAMILYOS_TEST_REDIS_ADDR` 时会自动跳过。

## 安全与部署

- 不要提交 `.env`、真实 `config.yaml`、JWT 密钥、内部 Token、短信 HMAC 密钥、OSS/模型 API Key 或数据库密码。
- Logic、Agent 和 Adapter 的内部 gRPC 端口仅允许可信网络访问；Gateway 应置于 HTTPS 和反向代理之后。
- 生产环境必须为 OpenSearch、Milvus、Neo4j、RocketMQ、MySQL 和 Redis 启用鉴权、TLS 或网络隔离。
- Compose 中的默认密码和 OpenSearch `DISABLE_SECURITY_PLUGIN=true` 仅适合本地开发。
- Refresh Token、验证码和内部 Token 不得写入日志；移动端凭证必须保存在安全存储中。
- 修改 `.proto` 后运行 `make proto-gen`，并同步更新 Python 生成代码和相关契约测试。
- Agent MySQL、Milvus、OpenSearch 和 Neo4j 之间不存在跨库事务，索引版本必须以 Logic/MySQL 状态为准，并保留失败补偿和重试监控。

## 许可证

仓库当前未在根目录声明统一许可证。若计划公开发布或供第三方使用，请先补充根目录 `LICENSE` 并更新本节。
