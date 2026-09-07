# FamilyOS

FamilyOS 是一个面向家庭场景的饮食与知识管理应用，提供用户认证、菜谱浏览、家庭菜单、购物清单、饮食偏好，以及基于个人/家庭文档的 AI 问答能力。

项目由 Go 后端服务和 Expo/React Native 移动端组成，后端通过 HTTP JSON 对外提供 API，内部使用 gRPC 连接业务服务与 Agent 服务。

> 当前仓库主要面向开发与联调。生产部署前请替换所有示例密钥、关闭开发环境的 OpenSearch 安全插件，并补充正式的部署、监控和备份方案。

## 功能概览

- 用户名密码登录、短信验证码登录、Access/Refresh Token 会话轮换
- 个人资料、饮食偏好和头像管理
- 菜谱分类、关键词搜索、菜谱详情与烹饪步骤计时
- 家庭创建、加入、成员管理和邀请口令
- 家庭菜单、菜单评价、饮食档案和购物清单
- 个人/家庭知识库文档上传、异步索引和处理状态追踪
- 基于 Query Rewrite + ReAct 的知识库问答，并返回可验证的文档引用

## 系统架构

```text
移动端 / curl / Postman
          │ HTTP JSON :8080
          ▼
Gateway Service（Gin）
          │ gRPC
          ├──────────────► Logic Service :50051
          │                    ├── MySQL（业务数据）
          │                    ├── Redis（验证码、Refresh Session）
          │                    └── OSS（可选，文档和头像）
          │
          └──────────────► Agent Service :50052（可选）
                               ├── MySQL（索引任务、会话、切片元数据）
                               ├── pgvector（向量索引）
                               ├── OpenSearch（BM25/IK 倒排索引，可选）
                               ├── RocketMQ（文档索引事件）
                               └── OpenAI-compatible Embedding/Chat API
```

Gateway 是客户端唯一需要访问的 HTTP 入口；Logic 和 Agent 的 gRPC 端口用于服务间通信或本地调试，不建议直接暴露到公网。

## 技术栈

- 后端：Go、Gin、gRPC、GORM、MySQL、Redis
- AI 与检索：CloudWeGo Eino、pgvector、OpenSearch、RocketMQ、OpenAI-compatible API
- 移动端：Expo SDK 56、React Native、TypeScript、React Navigation
- 协议：Protocol Buffers，源文件位于 [`proto/`](proto/)

## 仓库结构

```text
.
├── gateway-service/             # HTTP 网关与鉴权中间件
├── logic-service/               # 用户、家庭、菜谱、菜单等核心业务 gRPC 服务
├── agent-service/               # 文档索引 Worker 与 AI 问答 gRPC 服务
├── mobile-app/                  # Expo/React Native 移动端
├── proto/                       # gRPC/Protobuf 定义与生成代码
├── sql/                         # 数据库增量迁移脚本
├── opensearch/                  # IK Analyzer 镜像与词典配置
├── rocketmq/                    # RocketMQ Broker/Proxy 配置
├── docker-compose.infrastructure.yml
├── 接口文档.md                  # HTTP API 详细说明
└── Makefile                    # 常用开发命令
```

## 环境要求

- Go `1.26.4` 或兼容版本
- Node.js 与 npm（用于 Expo 移动端）
- Docker Desktop 或 Docker Engine + Compose v2
- MySQL 8.x：Logic 业务库和 Agent 任务库
- Redis 6.x 或更高版本
- （启用 RAG 时）pgvector、OpenSearch、RocketMQ
- （启用 AI 时）可访问的 Embedding 与 Chat OpenAI-compatible 接口

## 快速开始

### 1. 获取代码并准备 Go 依赖

```bash
git clone https://github.com/lijunsheng/familyos.git
cd familyos
go mod download
```

### 2. 启动基础设施

仓库提供的 Compose 文件会启动 pgvector、OpenSearch 和 RocketMQ：

```bash
docker compose -f docker-compose.infrastructure.yml up -d
docker compose -f docker-compose.infrastructure.yml ps
```

MySQL 和 Redis 不在该 Compose 文件中，请自行启动并创建数据库。至少需要：

- `familyos_logic`：Logic Service 业务数据
- `familyos_agent`：Agent Service 的索引任务、会话和切片元数据
- `familyos_agent_vector`：pgvector 数据库（启用 RAG 时）

### 3. 初始化数据库

`sql/` 中的脚本是按日期命名的增量迁移，执行顺序按文件名排序。脚本依赖项目已有基础表，不能替代基础表初始化；请先准备基础 schema，再执行迁移：

```bash
for file in sql/*.sql; do
  case "${file}" in
    *20260830_create_pgvector_document_vectors.sql) continue ;;
  esac
  echo "Applying ${file}"
  mysql --default-character-set=utf8mb4 -u<user> -p < "${file}"
done
```

其中 `familyos_agent` 相关脚本会显式切换数据库；被跳过的 `20260830_create_pgvector_document_vectors.sql` 应在启用 pgvector 的 PostgreSQL 数据库中单独执行：

```bash
psql "$FAMILYOS_AGENT_RAG_PGVECTOR_DSN" -f sql/20260830_create_pgvector_document_vectors.sql
```

生产环境请使用正式迁移工具或经过审核的发布脚本，不要盲目重复执行不可重复迁移。

### 4. 配置服务

复制示例配置，并按环境修改数据库、Redis、JWT、RocketMQ、OSS 和模型参数：

```bash
cp logic-service/config/config.yaml.example logic-service/config/config.yaml
cp gateway-service/config/config.yaml.example gateway-service/config/config.yaml
cp agent-service/config/config.yaml.example agent-service/config/config.yaml
cp .env.example .env
```

Go 服务不会自动读取 `.env` 文件；启动前请将变量导入当前 shell（或交由进程管理器注入）：

```bash
set -a
source .env
set +a
```

至少需要配置以下内容：

- Logic：`FAMILYOS_DATABASE_DSN`、`FAMILYOS_JWT_SECRET`、`FAMILYOS_SMS_CODE_HMAC_SECRET`、Redis 地址
- Gateway：与 Logic 完全一致的 JWT 密钥、`localhost:50051` 和 `localhost:50052`
- Agent：RocketMQ 地址及 Agent 数据库；启用 RAG 时再配置 Embedding、pgvector 和 Logic 内部令牌；启用问答时配置 Rewrite/Chat 模型密钥

`config.yaml` 和 `.env` 仅用于本地或部署环境，禁止提交真实凭证。Logic 与 Gateway 必须共享 JWT 密钥；Logic 与 Agent 的内部令牌也必须完全一致。

### 5. 启动后端

建议分别打开三个终端：

```bash
make run-logic
make run-gateway
cd agent-service && go run .
```

默认端口如下：

| 服务 | 地址 | 用途 |
| --- | --- | --- |
| Gateway | `http://localhost:8080` | 客户端 HTTP API |
| Logic | `localhost:50051` | 业务 gRPC |
| Agent | `localhost:50052` | AI 问答 gRPC（启用时） |
| pgvector | `localhost:5432` | 向量数据库 |
| OpenSearch | `http://localhost:9200` | 倒排检索 |
| RocketMQ NameServer | `localhost:9876` | 消息服务 |
| RocketMQ Proxy | `localhost:8083` | RocketMQ 客户端代理 |

验证 Gateway：

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

### 6. 启动移动端

```bash
cd mobile-app
npm install
npm start
```

也可以直接运行：

```bash
npm run android
npm run ios
npm run web
```

开发环境 API 地址在 [`mobile-app/src/config.ts`](mobile-app/src/config.ts) 中配置。真机调试时将 `DEV_HOST` 改为电脑局域网 IP；Android 模拟器通常使用 `10.0.2.2`，iOS 模拟器通常使用 `localhost`。修改后重新启动 Expo。

## API 文档

完整接口、请求示例、认证约定和业务状态码见 [`接口文档.md`](接口文档.md)。常用入口：

- `GET /health`：健康检查
- `POST /api/v1/auth/register`：用户注册
- `POST /api/v1/auth/login`：密码登录
- `POST /api/v1/auth/sms/login`：短信验证码登录/自动注册
- `GET /api/v1/dish/categories`：菜谱分类
- `GET /api/v1/dish/search`：菜谱搜索
- `GET /api/v1/family/my`：当前用户家庭
- `POST /api/v1/agent/chat/stream`：流式 AI 问答（需要 Agent 与 RAG 配置）

需要调试内部 gRPC 时，可使用 Protobuf 源文件或 Logic 服务注册的 gRPC reflection；生成代码位于 [`proto/gen/`](proto/gen/)。

## 常用开发命令

```bash
make install-deps  # 整理 Go 依赖并安装 protoc 插件
make proto-gen     # 根据 proto/ 重新生成 Go gRPC 代码
make proto-clean   # 删除生成代码（谨慎使用）
make build-logic   # 构建 Logic Service 到 deploy/logic-service
make build-gateway # 构建 Gateway Service 到 deploy/gateway-service
```

运行 Go 测试：

```bash
go test ./...
```

Redis/数据库集成测试默认会在缺少测试环境变量时跳过；需要运行时请按测试代码要求设置 `FAMILYOS_TEST_REDIS_ADDR` 等变量，并准备隔离的测试数据库。

## 安全与部署注意事项

- 不要提交 `.env`、真实 `config.yaml`、JWT 密钥、短信 HMAC 密钥、OSS/模型 API Key 或数据库密码。
- 生产环境必须启用 OpenSearch 安全插件与 TLS，Compose 中的 `DISABLE_SECURITY_PLUGIN=true` 仅适合本地开发。
- Gateway 应置于 HTTPS、反向代理和访问控制之后；Logic/Agent gRPC 端口只允许可信内网访问。
- Refresh Token、验证码等敏感凭证不得写入普通日志；客户端凭证由移动端安全存储负责保存。
- 修改 Protobuf 后应运行 `make proto-gen`，并将源文件与生成文件一起检查和提交。

## 许可证

仓库当前未在根目录声明统一许可证。若计划公开发布或供第三方使用，请补充根目录 `LICENSE` 并在此处更新说明。
