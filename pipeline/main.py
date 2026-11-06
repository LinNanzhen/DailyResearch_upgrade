"""Entry point: python -m pipeline.main [--days 3] [--no-llm] [--dry-run]"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import date, timedelta
from typing import Any, Dict, List

from . import analyze, fetch, render, score
from .llm import AgnesLLM, LLMError
from .settings import ROOT, load_profile, journal_tiers


def _load_env_local() -> None:
    """Local runs: read KEY=VALUE pairs from .env.local (git-ignored)."""
    path = ROOT / ".env.local"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def log(msg: str) -> None:
    print(msg, flush=True)


def run(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    tiers = journal_tiers(profile)
    today = date.today()
    days = int(args.days or profile["sources"].get("window_days", 3))
    start = today - timedelta(days=days)

    log(f"[1/6] 检索 {start} → {today}（{len(profile['sources']['journals'].get('tier_a', [])) + len(profile['sources']['journals'].get('tier_b', []))} 本期刊 + {len(profile['sources'].get('topic_queries', []))} 条主题检索）")
    papers, fstats = fetch.fetch_all(profile, start, today)
    log(f"      召回 {len(papers)} 篇（去重后；丢弃 {fstats['dropped_type']} 条非研究类型，{fstats['no_abstract']} 条无摘要）")

    seen = render.load_seen()
    feedback = render.apply_feedback(seen)
    papers = [p for p in papers if not render.is_blocked(p["id"])]
    papers = render.filter_seen(papers, seen)
    log(f"      去重历史（近 120 天已出现）+ 屏蔽后剩 {len(papers)} 篇")

    for p in papers:
        score.attach(p, profile, tiers, today)
    before = len(papers)
    papers = [p for p in papers if score.is_dental(p)]
    if before != len(papers):
        log(f"      牙科相关性过滤：去掉 {before - len(papers)} 篇大刊里的非口腔论文")
    papers = [p for p in papers if p["heuristic"] >= 18]
    papers.sort(key=lambda p: p["heuristic"], reverse=True)

    pool_cap = 36
    pool = papers[:pool_cap]
    log(f"[2/6] 粗排：{len(papers)} 篇 → 送模型 {len(pool)} 篇（阈值 18）")

    llm = AgnesLLM(
        base_url=os.environ.get("AGNES_BASE_URL") or profile["llm"]["base_url"],
        model=os.environ.get("AGNES_MODEL") or profile["llm"]["model"],
        temperature=float(profile["llm"].get("temperature", 0.2)),
        timeout=int(profile["llm"].get("timeout", 120)),
    )
    use_llm = llm.enabled and not args.no_llm
    scores: Dict[str, Dict[str, Any]] = {}
    if use_llm:
        batch_size = int(profile["llm"].get("batch_size", 12))
        abstract_chars = int(profile["llm"].get("abstract_chars", 1100))
        for i in range(0, len(pool), batch_size):
            batch = pool[i : i + batch_size]
            for attempt in range(2):
                try:
                    got = analyze.score_batch(llm, profile, batch, abstract_chars)
                    scores.update(got)
                    log(f"[3/6] 评分批次 {i // batch_size + 1}/{-(-len(pool) // batch_size)}：{len(batch)} 篇 → 合并 {len(got)} 条")
                    break
                except (LLMError, Exception) as exc:  # noqa: BLE001
                    log(f"      批次失败（{attempt + 1}/2）：{exc}")
        if not scores:
            use_llm = False
    else:
        log("[3/6] 跳过模型（无 AGNES_API_KEY 或 --no-llm），使用确定性排序")

    weights = profile["scoring"]["weights"]
    for p in papers:
        s = scores.get(p["id"])
        if s:
            weighted = (
                s["match"] * float(weights["match"])
                + s["novelty"] * float(weights["novelty"])
                + s["rigor"] * float(weights["rigor"])
                + s["impact"] * float(weights["impact"])
                + s["transfer"] * float(weights["transfer"])
            )
            final = 0.78 * weighted + 0.22 * p["heuristic"]
            if s.get("skip"):
                final *= 0.65
            p["score"] = {"final": round(final, 1), **{k: s[k] for k in ("match", "novelty", "rigor", "impact", "transfer")}}
            p.update({k: s[k] for k in ("cluster", "one_line", "so_what", "caution", "title_zh")})
            p["ai"] = True
        else:
            p["score"] = {"final": round(p["heuristic"] * (0.85 if use_llm else 1.0), 1)}
            p["cluster"] = p.get("domain", "未归类")
            p["one_line"] = ""
            p["so_what"] = ""
            p["caution"] = ""
            p["ai"] = False

    papers.sort(key=lambda p: p["score"]["final"], reverse=True)
    picks = score.select(papers, profile)
    musts, scans = picks["must_reads"], picks["scan"]
    log(f"[4/6] 选定：精读 {len(musts)} 篇 + 速览 {len(scans)} 篇")

    ai_ok = use_llm and any(p.get("ai") for p in musts + scans if p)
    for idx, m in enumerate(musts, start=1):
        if not ai_ok:
            break
        try:
            m["deep"] = analyze.deep_read(llm, profile, m)
            log(f"      精读卡 {idx}/{len(musts)} 生成完成")
        except (LLMError, Exception) as exc:  # noqa: BLE001
            log(f"      精读卡 {idx} 失败：{exc}")

    weekly = None
    if args.weekly or (today.weekday() == 6 and llm.enabled and not args.no_llm):
        try:
            recent = []
            for i in range(1, 8):
                d = today - timedelta(days=i)
                path = render.DAILY_DIR / f"{d.isoformat()}.json"
                if path.exists():
                    recent.append(json.loads(path.read_text(encoding="utf-8")))
            recent.append({"date": today.isoformat(), "must_read": musts[0] if musts else None, "must_reads": musts, "scan": scans})
            weekly = analyze.weekly_synthesis(llm, profile, recent)
            if weekly:
                weekly["date"] = today.isoformat()
                weekly["week"] = f"{today.isocalendar().year}-W{today.isocalendar().week:02d}"
                render.write_weekly(weekly["week"], weekly)
                log(f"[5/6] 周报生成：{weekly.get('headline', '')[:40]}")
        except (LLMError, Exception) as exc:  # noqa: BLE001
            log(f"      周报失败：{exc}")

    picks_all = musts + scans
    feed = render.apply_feedback(seen)  # consume again if new files landed
    backlog_items = render.update_backlog(
        render.load_backlog(),
        picks_all,
        int(profile["quota"].get("backlog_max_age_days", 21)),
        int(profile["quota"].get("backlog", 6)),
    )
    backlog = render.visible_backlog(backlog_items, int(profile["quota"].get("backlog", 6)))

    stats = {
        "candidates": fstats.get("ids", 0),
        "raw": fstats.get("raw", 0),
        "fetched": len(papers) + 0,
        "raw_dropped_type": fstats.get("dropped_type", 0),
        "no_abstract": fstats.get("no_abstract", 0),
        "gated": len(papers),
        "scored": len(scores),
        "shown": len([p for p in picks_all if p]),
        "ai": bool(ai_ok),
        "feedback_files": feedback.get("files", 0),
        "calls": llm.usage().get("calls", 0),
    }
    day = render.build_day(
        profile, musts, scans, backlog, stats,
        ai=bool(ai_ok),
        model=(os.environ.get("AGNES_MODEL") or profile["llm"]["model"]) if use_llm else "heuristic-only",
        usage=llm.usage(),
        weekly=weekly,
    )

    if args.dry_run:
        log("[dry-run] 不写文件。预览：")
        for p in picks_all:
            if p:
                log(f"  {p['score']['final']:>5} | {p.get('tier')} | {p['journal'][:34]:<34} | {p['title'][:70]}")
        return 0

    existing = render.DAILY_DIR / f"{today.isoformat()}.json"
    if not ai_ok and existing.exists():
        try:
            old = json.loads(existing.read_text(encoding="utf-8"))
        except Exception:
            old = {}
        if old.get("ai") and (1 + len(old.get("scan") or [])) >= 2:
            log("[guard] 本次模型不可用，保留已有的 AI 结果，不用降级结果覆盖")
            return 0

    render.mark_seen(seen, picks_all)
    render.save_seen(seen)
    render.save_backlog(backlog_items)
    path = render.write_daily(day)
    note = render.write_note(day)
    render.write_index(day["date"])

    if not args.no_email:
        try:
            from .emailer import send_day
            result = send_day(day, profile)
            if result.get("sent"):
                log(f"[email] 已发送 → {result.get('to')}（{result.get('provider')}）")
            else:
                log(f"[email] 跳过：{result.get('reason')}")
        except Exception as exc:  # noqa: BLE001 - email must never break the digest
            log(f"[email] 发送失败：{exc}")

    log(f"[6/6] 已写入 {path.relative_to(render.ROOT)} / {note.relative_to(render.ROOT)} / data/index.json")
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily dental literature digest")
    parser.add_argument("--days", type=int, default=0, help="回看天数（默认取 profile）")
    parser.add_argument("--no-llm", action="store_true", help="只用确定性排序（无网络模型）")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    parser.add_argument("--weekly", action="store_true", help="强制生成周报")
    parser.add_argument("--no-email", action="store_true", help="不发送邮件")
    parser.add_argument("--profile", default=None, help="自定义 profile.yml 路径")
    args = parser.parse_args(argv)
    _load_env_local()
    try:
        return run(args)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
