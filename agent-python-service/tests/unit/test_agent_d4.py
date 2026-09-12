import unittest

from familyos_agent.agent import validate_answer


class AgentD4Test(unittest.TestCase):
    def test_rejects_sensitive_output(self):
        self.assertEqual(validate_answer("token sk-abc123456789"), (False, "SENSITIVE_OUTPUT"))

    def test_rejects_invalid_citation(self):
        ok, code = validate_answer("答案", [{"chunk_id": "c1"}], [{"chunk_id": "c2"}])
        self.assertFalse(ok)
        self.assertEqual(code, "CITATION_NOT_FOUND")

    def test_rejects_allergen(self):
        self.assertEqual(validate_answer("加入花生", constraints={"allergens": ["花生"]}), (False, "DIETARY_CONSTRAINT_VIOLATION"))


if __name__ == "__main__":
    unittest.main()
