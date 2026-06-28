.PHONY: proto-gen proto-clean install-deps run-logic build-logic run-gateway build-gateway

# ===== Proto =====

PROTO_DIR := proto
PROTO_SRC := $(shell find $(PROTO_DIR) -name '*.proto' -not -path '*/gen/*')
GEN_DIR := proto/gen

proto-gen:
	@echo "Generating protobuf code..."
	@mkdir -p $(GEN_DIR)
	protoc \
		--proto_path=$(PROTO_DIR) \
		--go_out=$(GEN_DIR) \
		--go_opt=paths=source_relative \
		--go-grpc_out=$(GEN_DIR) \
		--go-grpc_opt=paths=source_relative \
		$(PROTO_SRC)
	@echo "Done."

proto-clean:
	@rm -rf $(GEN_DIR)
	@echo "Cleaned generated proto code."

# ===== Logic Service =====

run-logic:
	@cd logic-service && DB_DSN="$(DB_DSN)" JWT_SECRET="$(JWT_SECRET)" GRPC_PORT="$(GRPC_PORT)" go run .

build-logic:
	@cd logic-service && go build -o ../deploy/logic-service .

# ===== Gateway Service =====

run-gateway:
	@cd gateway-service && go run .

build-gateway:
	@cd gateway-service && go build -o ../deploy/gateway-service .

# ===== Deps =====

install-deps:
	@go mod tidy
	@go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
	@go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
	@echo "Dependencies installed."
