"""Repair an existing digest in place: python -m pipeline.repair --date 2026-11-11

Useful when a run produced empty or truncated deep-read cards and you don't want
to wait for tomorrow's crawl. Requires OPENCODE_API_KEY (MiMo-V2.6-Flash via
OpenCode Go). Cards that already pass the gate are left untouched.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from . import quality, render
from .settings import DAILY_DIR, load_profile


def repair_day(date: str, profile: Dict[str, Any], dry_run: bool = False, send_email: bool = False) -> int:
    path = DAILY_DIR / f"{date}.json"
    if not path.exists():
        print(f"找不到 {path}")
        return 2
    day = json.loads(path.read_text(encoding="utf-8"))
    musts: List[Dict[str, Any]] = day.get("must_reads") or ([day["must_read"]] if day.get("must_read") else [])

    judge = quality.make_judge(profile)
    repair_client = quality.make_repair(profile)
    primary = quality.primary_client(profile)
    if not repair_client and not (primary and primary.enabled):
        print("缺少 OPENCODE_API_KEY，且没有可用的 AGNES_API_KEY，无法修复。")
        return 2
    if not repair_client:
        print("提示：未配置 OPENCODE_API_KEY，本次用 Agnes 重试；配置后会自动改用 MiMo-V2.6-Flash。")
    print(f"评委：{judge.model if judge else '仅规则'}｜修复：{repair_client.model if repair_client else primary.model}｜共 {len(musts)} 篇精读")

    repaired = 0
    for i, m in enumerate(musts, start=1):
        before = quality.lint(m.get("deep"))
        deep, record = quality.ensure(
            m.get("deep"), m, profile,
            judge_client=judge,
            repair_client=repair_client,
            primary_client=primary,
        )
        m["deep"] = deep
        if deep:
            m["title_zh"] = deep.get("title_zh") or m.get("title_zh")
            m["one_line"] = deep.get("one_sentence") or m.get("one_line")
        status = "通过" if record["passed"] else "未过"
        print(f"  {i}. {before['score']:.0f} → {record['score']:.0f} 分，{status}"
              + (f"，由 {record['repaired_by']} 重写" if record.get("repaired_by") else ""))
        if record.get("repaired_by"):
            repaired += 1

    day["must_read"] = musts[0] if musts else None
    stats = day.setdefault("stats", {})
    stats["quality_repaired"] = repaired
    stats["quality_failed"] = len([m for m in musts if ((m.get("deep") or {}).get("quality") or {}).get("passed") is False])

    if dry_run:
        print("[dry-run] 不写文件")
        return 0

    render.write_daily(day)
    render.write_note(day)
    render.write_index(day["date"])
    print(f"已写回 data/daily/{date}.json 与 notes/{date}.md")

    if send_email:
        try:
            from .emailer import send_day
            result = send_day(day, profile)
            print(f"[email] {result}" if result.get("sent") else f"[email] 跳过：{result.get('reason')}")
        except Exception as exc:  # noqa: BLE001
            print(f"[email] 发送失败：{exc}")
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair deep-read cards in an existing digest")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--email", action="store_true", help="修好后重发一封邮件")
    args = parser.parse_args(argv)
    return repair_day(args.date, load_profile(), dry_run=args.dry_run, send_email=args.email)


if __name__ == "__main__":
    sys.exit(main())
