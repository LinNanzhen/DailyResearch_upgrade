"""Quality gate tests: lint, judge parsing, repair fallback."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import quality  # noqa: E402
from pipeline.settings import load_profile  # noqa: E402


def good_deep():
    return {
        "title_zh": "S-PRG 凝胶在高龋风险下的抗菌斑效应",
        "one_sentence": "在每日 8 次蔗糖挑战下，S-PRG 凝胶 7 天内仍显著抑制菌斑面积。",
        "question": "材料缓释的离子能否在高频糖暴露下持续抑制菌斑，而不是只在清洁后短时有效？",
        "design": "双盲随机 split-mouth 原位研究，三组材料对照，24 小时与 7 天两个时间点。",
        "sample_desc": "18 名志愿者佩戴含釉质块的口内装置。",
        "findings": [
            {"claim": "S-PRG 组菌斑面积显著低于对照", "evidence": "7 天时较浮石/水组低 38%（p<0.01）"},
            {"claim": "时间与材料存在交互作用", "evidence": "重复测量 ANOVA 交互项 p=0.03"},
        ],
        "effect": "组间差异 38%（p<0.01）",
        "relation": "推进 q3：材料通过改变菌斑微环境而非杀菌来影响龋病风险。",
        "why": "证明缓释材料可以在糖攻击下维持效果，改变防龋产品的评价方式。",
        "limitations": ["样本仅 18 人", "7 天随访偏短"],
        "transferable": "split-mouth 加蔗糖挑战的设计可迁移到种植体周材料评价。",
        "followups": [
            "离子释放曲线在 7 天后是否仍然维持？",
            "高龋风险人群的唾液缓冲能力是否改变结论？",
            "与氟化物联用是否协同？",
        ],
        "glossary": [{"en": "S-PRG", "cn": "表面预反应玻璃离子"}],
        "reading_minutes": 12,
    }


class TestLint(unittest.TestCase):
    def test_empty_card_fails(self):
        result = quality.lint(None)
        self.assertFalse(result["passed"])
        self.assertEqual(result["score"], 0)

    def test_all_empty_strings_fails(self):
        broken = {k: "" for k in ("title_zh", "one_sentence", "question", "design", "sample_desc",
                                  "effect", "relation", "why", "transferable")}
        broken.update({"findings": [], "limitations": [], "followups": [], "glossary": []})
        result = quality.lint(broken)
        self.assertFalse(result["passed"])
        self.assertTrue(result["critical"])
        self.assertGreater(len(result["problems"]), 3)

    def test_partial_card_fails(self):
        deep = good_deep()
        deep["findings"] = [{"claim": "只有一个结论", "evidence": ""}]
        deep["followups"] = deep["followups"][:2]
        result = quality.lint(deep)
        self.assertFalse(result["passed"])

    def test_good_card_passes(self):
        result = quality.lint(good_deep())
        self.assertTrue(result["passed"], result["problems"])
        self.assertGreaterEqual(result["score"], 90)

    def test_duplicate_evidence_is_penalised(self):
        deep = good_deep()
        deep["findings"] = [
            {"claim": "结论一", "evidence": "同一条证据"},
            {"claim": "结论二", "evidence": "同一条证据"},
        ]
        self.assertLess(quality.lint(deep)["score"], 100)

    def test_truncated_field(self):
        deep = good_deep()
        deep["design"] = "双盲随机 split-mouth 原位研究，三组材料对照，24 小时与 7 天两个时间点…"
        self.assertTrue(any("截断" in p for p in quality.lint(deep)["problems"]))


class FakeClient:
    def __init__(self, payload=None, model="mimo-v2.6-flash", enabled=True):
        self.payload = payload
        self.model = model
        self.enabled = enabled
        self.calls = 0

    def chat_json(self, messages, max_tokens=0):
        self.calls += 1
        if isinstance(self.payload, list):
            return self.payload.pop(0) if self.payload else {}
        return self.payload


class TestEnsure(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile()
        self.paper = {"title": "S-PRG gel trial", "journal": "J Dent", "abstract": "18 volunteers..."}

    def test_no_clients_returns_record(self):
        deep, record = quality.ensure(good_deep(), self.paper, self.profile)
        self.assertTrue(record["passed"])
        self.assertEqual(deep["quality"]["score"], record["score"])

    def test_judge_rejects_then_repair_fixes(self):
        bad_judge = FakeClient(payload=[
            {"complete": False, "faithful": True, "specific": False, "score": 40,
             "problems": ["缺少效应量", "追问不足"]},
            {"complete": True, "faithful": True, "specific": True, "score": 85, "problems": []},
        ])
        repair = FakeClient(model="mimo-v2.6-flash")
        with patch("pipeline.analyze.deep_read", return_value=good_deep()) as reader:
            deep, record = quality.ensure(good_deep(), self.paper, self.profile,
                                          judge_client=bad_judge, repair_client=repair)
        self.assertEqual(record["repaired_by"], "mimo-v2.6-flash")
        self.assertTrue(record["passed"])
        self.assertTrue(reader.called)
        issues = reader.call_args.kwargs.get("issues")
        self.assertTrue(issues)

    def test_repair_failure_keeps_original(self):
        repair = FakeClient(model="mimo-v2.6-flash")
        broken = {"title_zh": "", "findings": []}
        with patch("pipeline.analyze.deep_read", side_effect=RuntimeError("boom")):
            deep, record = quality.ensure(broken, self.paper, self.profile,
                                          judge_client=None, repair_client=repair)
        self.assertFalse(record["passed"])
        self.assertEqual(deep, broken)

    def test_judge_parsing(self):
        client = FakeClient(payload={"complete": True, "faithful": True, "specific": True,
                                     "score": 88, "problems": []})
        result = quality.judge(client, self.paper, good_deep())
        self.assertTrue(result["passed"])
        self.assertEqual(result["score"], 88.0)

    def test_judge_bad_score(self):
        client = FakeClient(payload={"complete": True, "faithful": False, "specific": True,
                                     "score": 95, "problems": ["编造了数字"]})
        result = quality.judge(client, self.paper, good_deep())
        self.assertFalse(result["passed"])


class TestHeaders(unittest.TestCase):
    def test_opencode_session_header(self):
        from pipeline.llm import AgnesLLM
        client = AgnesLLM(api_key="sk-test", base_url="https://opencode.ai/inference/go/openai/v1",
                          model="mimo-v2.6-flash", user_agent="daily-dental-digest/2.0")
        headers = client._headers()
        self.assertEqual(headers["Authorization"], "Bearer sk-test")
        self.assertIn("x-opencode-session", headers)
        self.assertEqual(headers["User-Agent"], "daily-dental-digest/2.0")

    def test_non_opencode_has_no_session_header(self):
        from pipeline.llm import AgnesLLM
        client = AgnesLLM(api_key="sk-test", base_url="https://apihub.agnes-ai.com/v1")
        self.assertNotIn("x-opencode-session", client._headers())


class TestClientFactory(unittest.TestCase):
    def test_missing_key(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(quality.make_client({"model": "mimo-v2.6-flash", "enabled": True}))

    def test_disabled(self):
        with patch.dict("os.environ", {"OPENCODE_API_KEY": "x"}, clear=True):
            self.assertIsNone(quality.make_client({"enabled": False}))


if __name__ == "__main__":
    unittest.main()
