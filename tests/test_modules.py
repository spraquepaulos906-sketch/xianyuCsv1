"""模块单测：情感分析 / 知识库 / 议价策略与行为开关 / 上下文与 badcase。

用 python -m unittest 运行，零额外依赖（unittest 为标准库）。
所有写库测试均落在临时目录，不污染 data/ 下的真实数据。
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

# 确保能导入项目根目录下的模块
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from sentiment import SentimentAnalyzer
from knowledge_base import KnowledgeBase
import config_manager
from context_manager import ChatContextManager


class TestSentimentAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = SentimentAnalyzer()

    def test_empty_text_is_neutral(self):
        r = self.analyzer.analyze("")
        self.assertEqual(r["label"], "neutral")
        self.assertEqual(r["score"], 0.0)

    def test_no_emotion_word_is_neutral(self):
        r = self.analyzer.analyze("123456 你好")
        self.assertEqual(r["label"], "neutral")

    def test_strong_negative(self):
        r = self.analyzer.analyze("这绝对是假货")
        self.assertEqual(r["label"], "negative")
        self.assertLess(r["score"], 0)

    def test_strong_positive(self):
        r = self.analyzer.analyze("太棒了")
        self.assertEqual(r["label"], "positive")
        self.assertGreater(r["score"], 0)

    def test_degree_amplifies(self):
        # 失望 -2.0 × 非常 1.7 = -3.4，比光说"失望"更负
        base = self.analyzer.analyze("失望")
        strong = self.analyzer.analyze("非常失望")
        self.assertLess(strong["score"], base["score"])

    def test_negation_flips_sign(self):
        # "没有失望" 应翻转"失望"的负面极性
        r = self.analyzer.analyze("没有失望")
        self.assertEqual(r["label"], "positive")


class TestKnowledgeBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.kb = KnowledgeBase(db_path=os.path.join(self._tmp.name, "knowledge.db"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_add_and_list(self):
        eid = self.kb.add("保修多久", "一年保修", "保修,质保", "售后")
        self.assertIsInstance(eid, int)
        entries = self.kb.list()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["question"], "保修多久")
        self.assertEqual(entries[0]["category"], "售后")

    def test_search_hits_relevant_entry(self):
        self.kb.add("支持七天无理由吗", "支持七天无理由退换", "无理由,退换", "售后")
        self.kb.add("发货用什么快递", "默认中通", "快递,发货", "物流")
        hits = self.kb.search("可以七天无理由退货吗")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["question"], "支持七天无理由吗")

    def test_disabled_entry_excluded_from_search(self):
        eid = self.kb.add("保修多久", "一年保修", "", "售后")
        self.kb.update(eid, enabled=0)
        hits = self.kb.search("保修多久")
        self.assertEqual(hits, [])

    def test_update_and_delete(self):
        eid = self.kb.add("保修多久", "一年", "", "")
        self.assertTrue(self.kb.update(eid, answer="三年保修"))
        self.assertEqual(self.kb.list()[0]["answer"], "三年保修")
        self.assertTrue(self.kb.delete(eid))
        self.assertEqual(self.kb.list(), [])


class TestConfigStrategy(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # 把 config.json 路径指到临时文件，避免污染真实配置
        patcher = mock.patch.object(
            config_manager, "CONFIG_PATH",
            os.path.join(self._tmp.name, "config.json"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_bargain_strategy(self):
        s = config_manager.get_bargain_strategy()
        self.assertTrue(s["enabled"])
        self.assertEqual(s["max_discount_ratio"], 0.10)
        self.assertTrue(s["tiers"])

    def test_save_and_reload_bargain_strategy(self):
        new_strategy = {
            "enabled": False,
            "max_discount_ratio": 0.20,
            "tiers": [{"round": 1, "ratio": 0.05}, {"round": 2, "ratio": 0.20}],
        }
        saved = config_manager.save_bargain_strategy(new_strategy)
        self.assertEqual(saved["max_discount_ratio"], 0.20)
        reloaded = config_manager.get_bargain_strategy()
        self.assertFalse(reloaded["enabled"])
        self.assertEqual(len(reloaded["tiers"]), 2)

    def test_behavior_default_and_save(self):
        b = config_manager.get_behavior()
        self.assertFalse(b["auto_manual_on_negative"])
        saved = config_manager.save_behavior({"auto_manual_on_negative": True})
        self.assertTrue(saved["auto_manual_on_negative"])
        self.assertTrue(config_manager.get_behavior()["auto_manual_on_negative"])


class TestContextAndBadcase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ctx = ChatContextManager(
            max_history=100, db_path=os.path.join(self._tmp.name, "chat_history.db")
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_message_with_sentiment_and_intent(self):
        self.ctx.add_message_by_chat(
            "chat1", "user1", "item1", "user", "太贵了",
            sentiment="negative", intent="price",
        )
        msgs = self.ctx.get_messages_by_chat("chat1")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["sentiment"], "negative")
        self.assertEqual(msgs[0]["intent"], "price")

    def test_bargain_count_increment(self):
        self.ctx.increment_bargain_count_by_chat("chat1")
        self.ctx.increment_bargain_count_by_chat("chat1")
        self.assertEqual(self.ctx.get_bargain_count_by_chat("chat1"), 2)

    def test_badcase_lifecycle(self):
        bcid = self.ctx.add_badcase(
            chat_id="chat1", user_id="user1", item_id="item1",
            user_msg="太贵了", bot_reply="可以小刀",
            intent="price", sentiment="negative",
        )
        self.assertIsNotNone(bcid)
        cases = self.ctx.list_badcases()
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["status"], "open")

        # 更新归类与状态
        self.assertTrue(self.ctx.update_badcase(bcid, category="买家质疑", status="resolved"))
        cases = self.ctx.list_badcases(status="resolved")
        self.assertEqual(cases[0]["category"], "买家质疑")

        # 按来源过滤
        self.assertEqual(self.ctx.list_badcases(source="群反馈"), [])
        self.assertEqual(len(self.ctx.list_badcases(source="日志复盘")), 1)

        # 删除
        self.assertTrue(self.ctx.delete_badcase(bcid))
        self.assertEqual(self.ctx.list_badcases(), [])


if __name__ == "__main__":
    unittest.main()
