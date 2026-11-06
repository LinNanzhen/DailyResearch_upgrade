"""Offline tests for email rendering and provider selection."""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import emailer  # noqa: E402
from pipeline.settings import load_profile  # noqa: E402


def sample_day(ai: bool = True):
    return {
        "date": "2026-11-06",
        "generated_at": "2026-11-06T07:35:00+08:00",
        "model": "agnes-2.5-flash",
        "ai": ai,
        "stats": {"candidates": 179, "gated": 156},
        "must_read": {
            "title": "Toward Sex-Specific Host Modulation Therapy",
            "title_zh": "迈向性别特异性的牙周炎宿主调节治疗",
            "journal": "Journal of dental research",
            "date": "2026-11-05",
            "design_label": "综述",
            "tier": "A",
            "cluster": "牙周与宿主免疫",
            "sample_note": "",
            "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
            "one_line": "生物学性别独立塑造牙周免疫。",
            "score": {"final": 84.2},
            "deep": {
                "question": "性别是否独立决定宿主反应通路？",
                "design": "叙述性综述",
                "sample_desc": "以小鼠证据为主",
                "findings": [{"claim": "男性依赖 IL-1β", "evidence": "阻断后骨丢失减少"}],
                "effect": "未报告合并效应量",
                "relation": "推进 q1",
                "limitations": ["无系统检索"],
                "transferable": "按性别分层报告",
                "followups": ["追问一？", "追问二？", "追问三？"],
                "reading_minutes": 16,
            },
        },
        "scan": [
            {
                "title": "Boosting Functional Dental Pulp Regeneration",
                "title_zh": "仿生水凝胶提升牙髓再生",
                "journal": "Acta biomaterialia",
                "date": "2026-11-04",
                "design_label": "动物实验",
                "url": "https://pubmed.ncbi.nlm.nih.gov/2/",
                "one_line": "水凝胶重塑干细胞龛。",
                "so_what": "可拆成两个干预环节。",
                "caution": "仅动物实验。",
                "score": {"final": 74},
            }
        ],
        "weekly": None,
    }


class TestEmailRender(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile()
        self.day = sample_day()

    def test_html_contains_core_content(self):
        html = emailer.render_email_html(self.day, self.profile)
        self.assertIn("迈向性别特异性的牙周炎宿主调节治疗", html)
        self.assertIn("https://pubmed.ncbi.nlm.nih.gov/1/", html)
        self.assertIn("主诉 / 问题", html)
        self.assertIn("读完回答这三个问题", html)
        self.assertIn("2026-11-06", html)
        self.assertNotIn("None", html)

    def test_text_version(self):
        text = emailer.render_email_text(self.day, self.profile)
        self.assertIn("【精读】", text)
        self.assertIn("【速览 02】", text)
        self.assertIn("追问一？", text)

    def test_subject(self):
        subj = emailer.subject_for(self.day)
        self.assertIn("2026-11-06", subj)
        self.assertIn("口腔文献日课", subj)
        self.assertLessEqual(len(subj), 70)

    def test_disabled_degrades(self):
        day = sample_day(ai=False)
        day["must_read"]["deep"] = None
        html = emailer.render_email_html(day, self.profile)
        self.assertIn("未接入模型", html)

    def test_empty_day_html_safe(self):
        html = emailer.render_email_html({"date": "2026-11-07", "must_read": None, "scan": []}, self.profile)
        self.assertIn("2026-11-07", html)


class TestProvider(unittest.TestCase):
    def test_none_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(emailer.resolve_provider({"provider": "auto"})[0], "none")

    def test_resend_preferred(self):
        env = {"RESEND_API_KEY": "re_123"}
        with patch.dict(os.environ, env, clear=True):
            provider, creds = emailer.resolve_provider({"provider": "auto"})
            self.assertEqual(provider, "resend")
            self.assertEqual(creds["key"], "re_123")

    def test_smtp_fallback(self):
        env = {"SMTP_HOST": "smtp.gmail.com", "SMTP_USER": "a@b.c", "SMTP_PASS": "x"}
        with patch.dict(os.environ, env, clear=True):
            provider, creds = emailer.resolve_provider({"provider": "auto"})
            self.assertEqual(provider, "smtp")
            self.assertEqual(creds["port"], "465")

    def test_explicit_provider_without_key(self):
        with patch.dict(os.environ, {"RESEND_API_KEY": "re_123"}, clear=True):
            self.assertEqual(emailer.resolve_provider({"provider": "smtp"})[0], "none")

    def test_send_skipped_when_disabled(self):
        result = emailer.send_day(sample_day(), {"delivery": {"email": {"enabled": False}}})
        self.assertFalse(result["sent"])

    def test_send_skipped_without_recipient(self):
        profile = load_profile()
        profile["delivery"]["email"]["to"] = ""
        with patch.dict(os.environ, {"RESEND_API_KEY": "re_123"}, clear=True):
            result = emailer.send_day(sample_day(), profile)
            self.assertFalse(result["sent"])
            self.assertIn("recipient", result["reason"])


if __name__ == "__main__":
    unittest.main()
