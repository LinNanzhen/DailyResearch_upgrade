"""LLM layer: batch scoring, deep read, weekly synthesis."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .llm import AgnesLLM, LLMError
from .score import DESIGN_POINTS

SYSTEM = (
    "你是口腔医学领域的资深研究者，长期做种植/牙周/微生物组/材料方向的课题，"
    "同时是严格的文献编辑。你的判断标准是：这篇论文能否让一个临床背景的研究生"
    "改变对机制的理解、改变实验设计、或改变临床决策。你厌恶空泛的'具有重要意义'式表述。"
    "所有输出必须是合法 JSON，中文表述，不要 markdown 代码块。"
)


def _profile_brief(profile: Dict[str, Any]) -> str:
    qs = "\n".join(f"- {q['id']}: {q['text']}" for q in profile.get("research_questions", []))
    domains = "、".join(d.get("name", "") for d in profile.get("domains", []))
    methods = "、".join(profile.get("methods_of_interest", []))
    return (
        f"研究者：{profile.get('identity', {}).get('name', '')}（{profile.get('identity', {}).get('stage', '')}）\n"
        f"关注领域（召回用，不代表都重要）：{domains}\n"
        f"正在追问的问题：\n{qs}\n"
        f"偏好方法：{methods}\n"
        f"不喜欢：{', '.join(profile.get('negative_patterns', []))}"
    )


def _paper_block(p: Dict[str, Any], idx: int, abstract_chars: int) -> str:
    return (
        f"[{idx}] id={p['id']}\n"
        f"标题：{p['title']}\n"
        f"期刊：{p['journal']}（{p.get('tier')} 级）｜日期：{p.get('date')}｜类型：{', '.join(p.get('pub_types', [])) or '未标注'}\n"
        f"粗判设计：{p.get('design_label')}｜样本：{p.get('sample_note') or '未提及'}｜被引：{p.get('cited_by')}\n"
        f"摘要：{p.get('abstract', '')[:abstract_chars]}"
    )


def score_batch(llm: AgnesLLM, profile: Dict[str, Any], batch: List[Dict[str, Any]], abstract_chars: int = 1100) -> Dict[str, Dict[str, Any]]:
    blocks = "\n\n".join(_paper_block(p, i, abstract_chars) for i, p in enumerate(batch))
    prompt = f"""{_profile_brief(profile)}

下面是今天候选的 {len(batch)} 篇论文。逐篇判断它对这个人的价值。

{blocks}

评分口径（0–100，允许 0–100 全区间，不要都打 70 分）：
- match：它是否推进了上面 q1–q5 中的某一个？直接回答机制/因果/疗效问题给高分；只是同义词相关给低分。
- novelty：是否提供新机制、新证据层级、新方法？增量式重复研究给 20–40。
- rigor：设计与样本能否撑住它的结论？（体外推到临床要扣分；n<30 的人体研究要扣分；无对照要扣分）
- impact：如果结论为真，是否会改变临床做法或领域共识？
- transfer：它的方法/概念能否迁移到 q1–q5 的课题上？（能直接借用实验设计的给高分）

输出 JSON 数组，每篇一个对象，字段：
i（必填，就是上面方括号里的序号）, id（可留空）, title_zh（≤30 字的中文标题）, match, novelty, rigor, impact, transfer, cluster（2–6 字主题簇，如"种植体周炎"）,
one_line（≤40 字：做了什么 + 结论，禁止"本文研究了"开头）,
so_what（≤35 字：对我的课题意味着什么；无关联写"仅背景"）,
caution（≤30 字：最可能被高估的地方，如"体外高浓度"、"单中心回顾"）,
skip（true/false：是否根本不值得占用今天的阅读位）
只输出数组。"""
    data = llm.chat_json([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], max_tokens=6200)
    rows = _rows_of(data)
    by_id = {str(p["id"]).strip().lower(): p for p in batch}
    out: Dict[str, Dict[str, Any]] = {}
    for pos, item in enumerate(rows):
        paper = _match_item(item, batch, by_id)
        if paper is None and len(rows) == len(batch):
            paper = batch[pos]  # models usually keep the input order
        if paper is None:
            continue
        out[paper["id"]] = _clean_scores(item)
    if not out and rows:
        print("[analyze] 0 matched. model sample: " + json.dumps(rows[0], ensure_ascii=False)[:400])
    return out


def _rows_of(data: Any) -> List[Dict[str, Any]]:
    """Normalise the many shapes a model uses for a list of scores."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("results", "papers", "data", "scores", "items", "list"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        numeric = {k: v for k, v in data.items() if isinstance(v, dict) and str(k).strip().isdigit()}
        if numeric:
            return [numeric[k] for k in sorted(numeric, key=lambda x: int(str(x)))]
        # a single score object
        if any(k in data for k in ("match", "novelty", "rigor")):
            return [data]
    return []


def _match_item(item: Dict[str, Any], batch: List[Dict[str, Any]], by_id: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Resolve a model row to a candidate.

    Models often echo the bracket index instead of the DOI, or upper-case the
    DOI. Both are fine: index first, then case-insensitive id.
    """
    idx = item.get("i", item.get("index", item.get("n")))
    try:
        if idx is not None and not isinstance(idx, bool):
            i = int(str(idx).strip())
            if 0 <= i < len(batch):
                return batch[i]
    except (TypeError, ValueError):
        pass
    pid = str(item.get("id") or "").strip().lower()
    if not pid:
        return None
    paper = by_id.get(pid)
    if paper:
        return paper
    # tolerate "id=..." / "pmid:..." decorations
    pid = pid.replace("id=", "").strip()
    return by_id.get(pid)


def _num(v: Any, default: float = 50.0) -> float:
    try:
        return max(0.0, min(100.0, float(v)))
    except (TypeError, ValueError):
        return default


def _clip(text: Any, n: int) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _clean_scores(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title_zh": _clip(item.get("title_zh"), 60),
        "match": _num(item.get("match")),
        "novelty": _num(item.get("novelty")),
        "rigor": _num(item.get("rigor")),
        "impact": _num(item.get("impact")),
        "transfer": _num(item.get("transfer")),
        "cluster": _clip(item.get("cluster"), 12) or "未归类",
        "one_line": _clip(item.get("one_line"), 60),
        "so_what": _clip(item.get("so_what"), 50),
        "caution": _clip(item.get("caution"), 40),
        "skip": bool(item.get("skip")),
    }


def deep_read(llm: AgnesLLM, profile: Dict[str, Any], paper: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"""{_profile_brief(profile)}

精读这篇论文，写成一份能让我 20 分钟内真正消化的结构化笔记。

标题：{paper['title']}
期刊：{paper['journal']}｜{paper.get('date')}｜设计粗判：{paper.get('design_label')}
摘要：{paper.get('abstract', '')[:2600]}

严格按下面的 JSON 输出（中文；不能从摘要确认的信息写"摘要未说明"，禁止编造数字）：
{{
 "title_zh": "准确的中文标题",
 "one_sentence": "≤40 字：一句话结论（含方向与强度）",
 "question": "它真正想回答的科学问题（不是'评估X'这种伪问题）",
 "design": "研究设计的一句话描述（对照、分组、随访）",
 "sample_desc": "样本量与来源（人群/动物/细胞），摘要未说明则写'摘要未说明'",
 "findings": [{{"claim": "结论点", "evidence": "支撑它的具体数据/统计；摘要没有数字时写它给出的具体现象或比较方向（例如"敲除组干细胞数量下降、胶原III排列紊乱"），不要重复写"摘要未说明""}}],
 "effect": "关键效应量与置信区间（原文有就抄，没有写'未报告'）",
 "relation": "与 q1–q5 的哪一条相关？是支持、反驳、还是提供新解释？",
 "why": "为什么它值得读（它改变了什么认知）",
 "limitations": ["作者承认的 + 你判断的，共 2–3 条"],
 "transferable": "哪个方法/设计/指标可以搬到我的课题",
 "followups": ["读完必须回答的 3 个追问，要具体到能查证"],
 "glossary": [{{"en": "term", "cn": "中文"}}],
 "reading_minutes": 12
}}
只输出对象。"""
    data = llm.chat_json([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], max_tokens=2600)
    if not isinstance(data, dict):
        raise LLMError("deep read returned non-object")
    return _clean_deep(data)


def _clean_deep(d: Dict[str, Any]) -> Dict[str, Any]:
    findings = []
    for f in d.get("findings") or []:
        if isinstance(f, dict):
            findings.append({"claim": _clip(f.get("claim"), 120), "evidence": _clip(f.get("evidence"), 160)})
        elif isinstance(f, str):
            findings.append({"claim": _clip(f, 120), "evidence": ""})
    followups = [_clip(x, 90) for x in (d.get("followups") or []) if str(x).strip()][:3]
    limits = [_clip(x, 100) for x in (d.get("limitations") or []) if str(x).strip()][:3]
    glossary = []
    for g in d.get("glossary") or []:
        if isinstance(g, dict) and g.get("en"):
            glossary.append({"en": _clip(g.get("en"), 40), "cn": _clip(g.get("cn"), 40)})
    try:
        minutes = int(d.get("reading_minutes") or 12)
    except (TypeError, ValueError):
        minutes = 12
    return {
        "title_zh": _clip(d.get("title_zh"), 120),
        "one_sentence": _clip(d.get("one_sentence"), 60),
        "question": _clip(d.get("question"), 200),
        "design": _clip(d.get("design"), 200),
        "sample_desc": _clip(d.get("sample_desc"), 160),
        "findings": findings[:4],
        "effect": _clip(d.get("effect"), 160),
        "relation": _clip(d.get("relation"), 200),
        "why": _clip(d.get("why"), 200),
        "limitations": limits,
        "transferable": _clip(d.get("transferable"), 160),
        "followups": followups,
        "glossary": glossary[:6],
        "reading_minutes": max(5, min(40, minutes)),
    }


def weekly_synthesis(llm: AgnesLLM, profile: Dict[str, Any], days: List[Dict[str, Any]]) -> Dict[str, Any]:
    lines = []
    for day in days:
        for sec in ["must_read", "scan"]:
            for p in ([day.get(sec)] if sec == "must_read" else day.get(sec, [])):
                if not p:
                    continue
                lines.append(f"- {p.get('date')}｜{p.get('cluster')}｜{p.get('title')}｜{p.get('one_line')}")
    if not lines:
        return {}
    prompt = f"""{_profile_brief(profile)}

这是过去一周进入我视野的论文（已按重要性筛过）：
{chr(10).join(lines)}

请做一次「领域地图」综述，帮我建立学科思维，而不是再列一遍标题。输出 JSON：
{{
 "headline": "≤30 字：这一周这个领域最重要的一件事",
 "clusters": [{{"name": "主题簇", "n": 篇数, "insight": "≤60 字：这簇在推进什么"}}],
 "tension": {{"a": "一种观点/证据", "b": "相反的观点/证据", "note": "≤50 字：争议真正的分歧点"}},
 "method_shift": "≤50 字：方法层面正在发生什么迁移",
 "gaps": ["3 个目前没人做好、我可以做的空白（每个 ≤40 字）"],
 "next_watch": "≤40 字：下周该盯什么"
}}
只输出对象。"""
    data = llm.chat_json([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], max_tokens=1600)
    if not isinstance(data, dict):
        return {}
    return {
        "headline": _clip(data.get("headline"), 60),
        "clusters": [
            {"name": _clip(c.get("name"), 20), "n": c.get("n") or 0, "insight": _clip(c.get("insight"), 100)}
            for c in (data.get("clusters") or []) if isinstance(c, dict)
        ][:5],
        "tension": {
            "a": _clip((data.get("tension") or {}).get("a"), 100),
            "b": _clip((data.get("tension") or {}).get("b"), 100),
            "note": _clip((data.get("tension") or {}).get("note"), 100),
        } if isinstance(data.get("tension"), dict) else None,
        "method_shift": _clip(data.get("method_shift"), 100),
        "gaps": [_clip(g, 80) for g in (data.get("gaps") or [])][:3],
        "next_watch": _clip(data.get("next_watch"), 80),
    }
