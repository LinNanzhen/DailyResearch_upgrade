"""Shared paths / config loading for the daily literature pipeline."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DAILY_DIR = DATA_DIR / "daily"
NOTES_DIR = ROOT / "notes"
STATE_DIR = ROOT / "state"
FEEDBACK_DIR = ROOT / "feedback"


def _deep_defaults(profile: Dict[str, Any]) -> Dict[str, Any]:
    profile.setdefault("quota", {"must_read": 1, "scan": 3, "backlog": 6, "backlog_max_age_days": 21})
    profile.setdefault("scoring", {"weights": {"match": 0.4, "novelty": 0.2, "rigor": 0.18, "impact": 0.12, "transfer": 0.1}})
    profile.setdefault("sources", {})
    profile["sources"].setdefault("window_days", 3)
    profile["sources"].setdefault("max_candidates", 220)
    profile["sources"].setdefault("journals", {"tier_a": [], "tier_b": []})
    profile["sources"].setdefault("topic_queries", [])
    profile.setdefault("llm", {})
    profile["llm"].setdefault("base_url", "https://apihub.agnes-ai.com/v1")
    profile["llm"].setdefault("model", "agnes-2.5-flash")
    profile["llm"].setdefault("batch_size", 12)
    profile["llm"].setdefault("abstract_chars", 1100)
    profile["llm"].setdefault("temperature", 0.2)
    profile["llm"].setdefault("timeout", 120)
    return profile


def load_profile(path: str | os.PathLike | None = None) -> Dict[str, Any]:
    p = Path(path) if path else CONFIG_DIR / "profile.yml"
    with open(p, "r", encoding="utf-8") as f:
        profile = yaml.safe_load(f) or {}
    return _deep_defaults(profile)


def journal_tiers(profile: Dict[str, Any]) -> Dict[str, str]:
    """lower-cased journal name -> A / B"""
    out: Dict[str, str] = {}
    journals = profile["sources"]["journals"]
    for name in journals.get("tier_a", []):
        out[str(name).strip().lower()] = "A"
    for name in journals.get("tier_b", []):
        out[str(name).strip().lower()] = "B"
    return out


def env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}
