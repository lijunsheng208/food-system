import unittest
from evaluation.scripts.import_dishes import stable_id

class ImportDishesTest(unittest.TestCase):
    # 稳定路径必须映射为稳定且不重复的 ID。
    def test_stable_id(self):
        self.assertEqual(stable_id("a.md"), stable_id("a.md")); self.assertNotEqual(stable_id("a.md"), stable_id("b.md"))
