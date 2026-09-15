import unittest
from unittest.mock import patch

from familyos_agent.agent import PrometheusAgentMetrics, validate_answer


class FakeTimer:
    """模拟要求先进入再退出的 Prometheus Timer。"""

    def __init__(self):
        """初始化 Timer 生命周期状态。"""
        self.started = False
        self.finished = False

    def __enter__(self):
        """记录 Timer 已经开始计时。"""
        self.started = True
        return self

    def __exit__(self, exc_type, exc, traceback):
        """拒绝结束尚未启动的 Timer，并记录正常结束。"""
        if not self.started:
            raise AttributeError("Timer 尚未启动")
        self.finished = True


class FakeMetric:
    """提供 Prometheus 指标测试所需的最小接口。"""

    def __init__(self):
        """保存该指标创建的所有 Timer。"""
        self.timers = []

    def time(self):
        """创建并记录新的计时器。"""
        timer = FakeTimer()
        self.timers.append(timer)
        return timer

    def labels(self, **labels):
        """返回当前指标以模拟标签绑定。"""
        return self

    def inc(self, amount=1):
        """模拟计数器递增。"""
        return None

    def observe(self, value):
        """模拟直方图记录。"""
        return None


class AgentD4Test(unittest.TestCase):
    def test_rejects_sensitive_output(self):
        self.assertEqual(validate_answer("token sk-abc123456789"), (False, "SENSITIVE_OUTPUT"))

    def test_rejects_invalid_citation(self):
        ok, code = validate_answer("答案", [{"chunk_id": "c1"}], [{"chunk_id": "c2"}])
        self.assertFalse(ok)
        self.assertEqual(code, "CITATION_NOT_FOUND")

    def test_rejects_allergen(self):
        self.assertEqual(validate_answer("加入花生", constraints={"allergens": ["花生"]}), (False, "DIETARY_CONSTRAINT_VIOLATION"))

    def test_rejects_avoided_ingredient_alongside_allergens(self):
        """验证存在过敏原时仍会同时校验用户的主动忌口。"""
        constraints = {"allergens": ["花生"], "avoided_ingredients": ["辣椒"]}
        self.assertEqual(validate_answer("加入辣椒", constraints=constraints), (False, "DIETARY_CONSTRAINT_VIOLATION"))

    def test_first_token_timer_is_started_before_finishing(self):
        """验证首 token Timer 已进入计时状态，避免首次输出时缺少 _start。"""
        metrics = {}

        def create_metric(name, description, labels=None):
            """按指标名称创建并保存测试指标。"""
            metric = FakeMetric()
            metrics[name] = metric
            return metric

        with patch("prometheus_client.Counter", side_effect=create_metric), patch("prometheus_client.Histogram", side_effect=create_metric):
            recorder = PrometheusAgentMetrics()

        recorder.start("r1")
        first_token_timer = metrics["familyos_agent_first_token_seconds"].timers[0]
        self.assertTrue(first_token_timer.started)

        recorder.first_token("r1")
        recorder.finish("r1", "completed")

        self.assertTrue(first_token_timer.finished)


if __name__ == "__main__":
    unittest.main()
