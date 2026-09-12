"""D4 Agent 运行指标和 Tool 审计日志钩子。"""

import logging
import time
from collections import Counter
from typing import Any, Mapping

logger = logging.getLogger("familyos_agent.audit")


def configure_tracing(endpoint: str = "") -> None:
    """配置 OTLP gRPC exporter；未配置 endpoint 时保留默认 no-op tracer。"""
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        provider = TracerProvider(resource=Resource.create({"service.name": "familyos-agent"}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
        trace.set_tracer_provider(provider)
    except ImportError as exc:
        raise RuntimeError("配置 OTLP endpoint 需要安装 OpenTelemetry SDK 和 OTLP exporter") from exc


def trace_run(request_id: str) -> Any:
    """创建可选 OpenTelemetry span，未配置 SDK 时安全降级为空上下文。"""
    try:
        from opentelemetry import trace
        return trace.get_tracer("familyos-agent").start_as_current_span("agent.run", attributes={"request.id": request_id})
    except ImportError:
        from contextlib import nullcontext
        return nullcontext()


class AgentMetrics:
    """提供进程内计数和耗时统计，便于接入现有监控系统。"""

    def __init__(self) -> None:
        self.counters: Counter[str] = Counter()
        self._started: dict[str, float] = {}

    def start(self, request_id: str) -> None:
        """记录一次 Graph Run 开始时间。"""
        self._started[request_id] = time.monotonic()
        self.counters["graph_runs_total"] += 1

    def finish(self, request_id: str, status: str) -> None:
        """记录 Graph Run 终态和完整响应次数。"""
        self.counters["graph_runs_%s" % status] += 1
        self._started.pop(request_id, None)

    def tool(self, name: str, status: str) -> None:
        """记录 Tool 调用结果，不记录完整参数和个人资料。"""
        self.counters["tool_%s_%s" % (name, status)] += 1
        logger.info("tool_audit name=%s status=%s", name, status)


class PrometheusAgentMetrics(AgentMetrics):
    """将 Agent 指标导出为 Prometheus Counter 和 Histogram。"""

    def __init__(self) -> None:
        super().__init__()
        try:
            from prometheus_client import Counter, Histogram
        except ImportError as exc:
            raise RuntimeError("启用 Prometheus 指标需要安装 prometheus-client") from exc
        self._runs = Counter("familyos_agent_runs_total", "Agent runs", ["status"])
        self._tools = Counter("familyos_agent_tool_calls_total", "Tool calls", ["tool", "status"])
        self._nodes = Histogram("familyos_agent_node_duration_seconds", "Agent node duration", ["node"])
        self._tokens = Counter("familyos_agent_tokens_total", "Model tokens", ["kind"])
        self._duration = Histogram("familyos_agent_run_duration_seconds", "Agent run duration")
        self._first_token = Histogram("familyos_agent_first_token_seconds", "Time to first answer token")
        self._run_timers: dict[str, Any] = {}
        self._first_token_timers: dict[str, Any] = {}

    def start(self, request_id: str) -> None:
        """记录 Prometheus Run 开始时间。"""
        super().start(request_id)
        self._run_timers[request_id] = self._duration.time()
        self._run_timers[request_id].__enter__()
        self._first_token_timers[request_id] = self._first_token.time()

    def first_token(self, request_id: str) -> None:
        """结束首 token 计时，每个请求只记录一次。"""
        timer = self._first_token_timers.pop(request_id, None)
        if timer is not None:
            timer.__exit__(None, None, None)

    def finish(self, request_id: str, status: str) -> None:
        """记录终态计数并结束响应耗时观察。"""
        super().finish(request_id, status)
        self._runs.labels(status=status).inc()
        timer = self._run_timers.pop(request_id, None)
        if timer is not None:
            timer.__exit__(None, None, None)
        self._first_token_timers.pop(request_id, None)

    def tool(self, name: str, status: str) -> None:
        """记录脱敏 Tool 标签，禁止把参数和用户数据放入指标。"""
        super().tool(name, status)
        self._tools.labels(tool=name, status=status).inc()

    def node(self, name: str, duration: float) -> None:
        """记录节点耗时，节点名不包含用户输入。"""
        self._nodes.labels(node=name).observe(max(0.0, duration))

    def tokens(self, prompt: int = 0, completion: int = 0) -> None:
        """记录模型返回的 usage_metadata，缺失时不估算。"""
        if prompt > 0:
            self._tokens.labels(kind="prompt").inc(prompt)
        if completion > 0:
            self._tokens.labels(kind="completion").inc(completion)
