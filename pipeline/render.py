"""Output layer: JSON for the site, Markdown notes for the vault, index, state."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .settings import DAILY_DIR, DATA_DIR, NOTES_DIR, ROOT, STATE_DIR

CST = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(CST).replace(microsecond=0).isoformat()


def _read(path: Path, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def paper_payload(p: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "id", "pmid", "doi", "title", "title_zh", "journal", "date", "authors", "url", "pmcid",
        "cited_by", "design", "design_label", "design_level", "sample_n", "sample_note",
        "tier", "domain", "methods", "pub_types", "is_open_access", "cluster",
        "one_line", "so_what", "caution", "score", "heuristic", "breakdown",
    ]
    out = {k: p.get(k) for k in keys}
    out["abstract"] = (p.get("abstract") or "")[:2400]
    out["tags"] = (p.get("keywords") or [])[:6]
    return out


def build_day(
    profile: Dict[str, Any],
    must: Optional[Dict[str, Any]],
    scans: List[Dict[str, Any]],
    backlog: List[Dict[str, Any]],
    stats: Dict[str, Any],
    ai: bool,
    model: str,
    usage: Dict[str, int],
    weekly: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    def pack(p: Dict[str, Any]) -> Dict[str, Any]:
        base = paper_payload(p)
        if p.get("deep"):
            base["deep"] = p["deep"]
            if p["deep"].get("title_zh"):
                base["title_zh"] = p["deep"]["title_zh"]
            if p["deep"].get("one_sentence") and not base.get("one_line"):
                base["one_line"] = p["deep"]["one_sentence"]
        return base

    return {
        "date": date.today().isoformat(),
        "generated_at": now_iso(),
        "model": model,
        "ai": ai,
        "usage": usage,
        "stats": stats,
        "must_read": pack(must) if must else None,
        "scan": [pack(p) for p in scans],
        "backlog": backlog,
        "weekly": weekly,
        "profile": {
            "name": profile.get("identity", {}).get("name", ""),
            "questions": [{"id": q["id"], "text": q["text"]} for q in profile.get("research_questions", [])],
        },
    }


def write_daily(day: Dict[str, Any]) -> Path:
    path = DAILY_DIR / f"{day['date']}.json"
    _write(path, day)
    return path


def write_weekly(week_id: str, payload: Dict[str, Any]) -> Path:
    path = DATA_DIR / "weekly" / f"{week_id}.json"
    _write(path, payload)
    return path


def write_index(latest: Optional[str] = None) -> Dict[str, Any]:
    days = []
    for f in sorted(DAILY_DIR.glob("*.json"), reverse=True)[:90]:
        d = _read(f, {})
        if not d:
            continue
        must = d.get("must_read") or {}
        days.append({
            "date": d.get("date", f.stem),
            "must_title": must.get("title", ""),
            "must_title_zh": must.get("title_zh") or must.get("title", ""),
            "cluster": must.get("cluster", ""),
            "count": (1 if must else 0) + len(d.get("scan") or []),
            "ai": bool(d.get("ai")),
        })
    weeks = []
    for f in sorted((DATA_DIR / "weekly").glob("*.json"), reverse=True)[:12]:
        w = _read(f, {})
        if w:
            weeks.append({"id": f.stem, "date": w.get("date", ""), "headline": w.get("headline", "")})
    index = {
        "updated_at": now_iso(),
        "latest": latest or (days[0]["date"] if days else None),
        "days": days,
        "weeks": weeks,
    }
    _write(DATA_DIR / "index.json", index)
    return index


# ---------------------------------------------------------------- backlog / seen
def load_backlog() -> List[Dict[str, Any]]:
    return _read(STATE_DIR / "backlog.json", {"items": []}).get("items", [])


def save_backlog(items: List[Dict[str, Any]]) -> None:
    _write(STATE_DIR / "backlog.json", {"updated_at": now_iso(), "items": items})


def update_backlog(items: List[Dict[str, Any]], picks: List[Dict[str, Any]], max_age: int, quota: int) -> List[Dict[str, Any]]:
    today = date.today()
    pick_ids = {p["id"] for p in picks if p}
    kept = []
    for it in items:
        if it.get("id") in pick_ids:
            continue
        try:
            age = (today - date.fromisoformat(it.get("date_shown", ""))).days
        except Exception:
            age = 0
        if age > max_age:
            continue
        it["days_waiting"] = max(0, age)
        kept.append(it)
    for p in picks:
        if not p or p.get("deep"):
            continue  # deep reads are consumed today; no need to resurface
        kept.append({
            "id": p["id"],
            "title": p.get("title", ""),
            "journal": p.get("journal", ""),
            "date_shown": today.isoformat(),
            "score": (p.get("score") or {}).get("final", 0),
            "one_line": p.get("one_line", ""),
            "cluster": p.get("cluster", ""),
            "url": p.get("url", ""),
            "days_waiting": 0,
        })
    kept.sort(key=lambda x: (-(x.get("days_waiting") or 0), -(x.get("score") or 0)))
    return kept[: max(quota * 2, 8)]


def visible_backlog(items: List[Dict[str, Any]], quota: int) -> List[Dict[str, Any]]:
    items = [i for i in items if (i.get("days_waiting") or 0) >= 1]
    return items[:quota]


def load_seen() -> Dict[str, Any]:
    return _read(STATE_DIR / "seen.json", {"papers": {}})


def save_seen(seen: Dict[str, Any]) -> None:
    _write(STATE_DIR / "seen.json", seen)


def mark_seen(seen: Dict[str, Any], papers: List[Dict[str, Any]]) -> None:
    today = date.today().isoformat()
    for p in papers:
        if not p:
            continue
        rec = seen["papers"].get(p["id"]) or {"first_seen": today, "times": 0}
        rec["last_shown"] = today
        rec["times"] = int(rec.get("times", 0)) + 1
        rec["title"] = p.get("title", "")
        seen["papers"][p["id"]] = rec
    # prune very old entries
    cutoff = (date.today() - timedelta(days=365)).isoformat()
    seen["papers"] = {k: v for k, v in seen["papers"].items() if (v.get("last_shown") or "") >= cutoff}


def filter_seen(papers: List[Dict[str, Any]], seen: Dict[str, Any], within_days: int = 120) -> List[Dict[str, Any]]:
    cutoff = (date.today() - timedelta(days=within_days)).isoformat()
    recent = {k for k, v in seen.get("papers", {}).items() if (v.get("last_shown") or "") >= cutoff}
    return [p for p in papers if p["id"] not in recent]


def apply_feedback(seen: Dict[str, Any], blocked_path: Path = STATE_DIR / "blocked.json") -> Dict[str, int]:
    """Consume feedback/inbox/*.json produced by the web page; dismissals become permanent."""
    inbox = ROOT / "feedback" / "inbox"
    blocked = _read(blocked_path, {"ids": []})
    handled = 0
    if not inbox.exists():
        return {"files": 0, "dismissed": 0, "read": 0}
    for f in sorted(inbox.glob("*.json")):
        payload = _read(f, {})
        for pid in payload.get("dismissed", []):
            if pid not in blocked["ids"]:
                blocked["ids"].append(pid)
        for pid in payload.get("read", []) + payload.get("saved", []):
            rec = seen["papers"].get(pid) or {"first_seen": date.today().isoformat(), "times": 0}
            rec["read"] = True
            seen["papers"][pid] = rec
        handled += 1
        try:
            f.rename(f.with_suffix(".json.done"))
        except Exception:
            pass
    _write(blocked_path, blocked)
    return {"files": handled, "dismissed": len(blocked["ids"]), "read": 0}


def is_blocked(pid: str) -> bool:
    return pid in set(_read(STATE_DIR / "blocked.json", {"ids": []}).get("ids", []))


# ---------------------------------------------------------------- markdown note
def write_note(day: Dict[str, Any]) -> Path:
    must = day.get("must_read") or {}
    deep = must.get("deep") or {}
    lines: List[str] = [
        "---",
        f"date: {day['date']}",
        "type: daily-literature",
        f"model: {day.get('model', '')}",
        "tags: [literature, 口腔医学]",
        "---",
        "",
        f"# {day['date']}｜今日 1 篇精读 + {len(day.get('scan') or [])} 篇速览",
        "",
        f"> 候选 {day.get('stats', {}).get('fetched', '?')} 篇 → 通过筛选 {day.get('stats', {}).get('gated', '?')} 篇 → 今日呈现 {(1 if must else 0) + len(day.get('scan') or [])} 篇。",
        "",
    ]
    if must:
        lines += [
            f"## 精读｜{must.get('title_zh') or must.get('title')}",
            "",
            f"- 期刊：{must.get('journal')}（{must.get('tier')} 级）｜{must.get('date')}",
            f"- 设计：{must.get('design_label')}｜样本：{must.get('sample_note') or '未提及'}",
            f"- 评分：{must.get('score', {}).get('final', '?')}/100",
            f"- 链接：{must.get('url')}",
            "",
        ]
        if deep:
            lines += [
                f"**一句话**：{must.get('one_line', '')}",
                "",
                f"**研究问题**：{deep.get('question', '')}",
                "",
                f"**设计与样本**：{deep.get('design', '')}；{deep.get('sample_desc', '')}",
                "",
            ]
            if deep.get("findings"):
                lines.append("**关键证据**")
                lines.append("")
                for f in deep["findings"]:
                    lines.append(f"- {f.get('claim', '')} —— {f.get('evidence', '')}")
                lines.append("")
            lines += [
                f"**效应量**：{deep.get('effect', '')}",
                "",
                f"**与我的课题**：{deep.get('relation', '')}",
                "",
                f"**局限**：{'；'.join(deep.get('limitations') or [])}",
                "",
                f"**可迁移**：{deep.get('transferable', '')}",
                "",
                "**三个追问**",
                "",
            ]
            for q in deep.get("followups") or []:
                lines.append(f"- [ ] {q}")
            lines.append("")
            if deep.get("glossary"):
                lines.append("**术语**：" + "；".join(f"{g['en']} = {g['cn']}" for g in deep["glossary"]))
                lines.append("")
        else:
            lines += [
                "> 本次未启用模型，没有生成精读卡。以下为摘要原文。",
                "",
                f"{must.get('abstract', '')[:1200]}",
                "",
            ]
    if day.get("scan"):
        lines += ["## 速览", ""]
        for p in day["scan"]:
            lines += [
                f"### {p.get('title')}",
                f"- {p.get('journal')}｜{p.get('date')}｜{p.get('design_label')}｜{p.get('score', {}).get('final', '?')}/100",
                f"- {p.get('one_line', '')}",
                f"- 对我：{p.get('so_what', '')}（{p.get('caution', '')}）",
                f"- {p.get('url')}",
                "",
            ]
    if day.get("weekly"):
        w = day["weekly"]
        lines += ["## 本周领域地图", "", f"**{w.get('headline', '')}**", ""]
        for c in w.get("clusters") or []:
            lines.append(f"- {c.get('name')}（{c.get('n')} 篇）：{c.get('insight')}")
        if w.get("tension"):
            lines += ["", f"**争议**：{w['tension'].get('a')} ↔ {w['tension'].get('b')}。{w['tension'].get('note')}"]
        lines += ["", f"**方法迁移**：{w.get('method_shift', '')}", "", "**空白**："]
        for g in w.get("gaps") or []:
            lines.append(f"- {g}")
        lines.append("")
    path = NOTES_DIR / f"{day['date']}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
