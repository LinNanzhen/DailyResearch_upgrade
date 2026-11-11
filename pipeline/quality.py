"""Quality gate for deep-read cards.

Three layers, cheapest first:

1. `lint`  — deterministic checks (empty fields, placeholders, thin evidence,
   truncated text). Always runs, no API key, never fabricates.
2. `judge` — an OpenCode Go model reads the abstract and the card, and returns
   {complete, faithful, specific, score, problems}. Optional.
3. `repair` — if the card fails, regenerate it with MiMo-V2.6-Flash (OpenCode Go)
   using the judge/lint problems as extra instructions, then re-check once.

The result is stored on `deep["quality"]` so the page and the email can show
whether a card was repaired, and the run log says so too.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .llm import AgnesLLM, LLMError

# field -> minimum characters for a card that is actually readable
REQUIRED_FIELDS = [
    ("one_sentence", 12),
    ("question", 20),
    ("design", 30),
    ("relation", 20),
    ("why", 15),
    ("transferable", 12),
]

PLACEHOLDER_RE = re.compile(
    r"^(n/?a|none|null|undefined|unknown|tbd|todo|未说明|摘要未说明|未报告|未知|无|待补充|省略|\.{3,}|…)$",
    re.I,
)
TRUNCATED_RE = re.compile(r"(\.{3,}|…)$")

JUDGE_SYSTEM = (
    "你是口腔医学期刊的审稿编辑，负责验收 AI 写的精读卡。"
    "你只判断三件事：是否完整（字段齐全、有具体内容）、是否忠实（没有摘要之外的数字或结论）、"
    "是否具体（能落到分组、样本、效应量或机制，而不是空话）。"
    "只输出 JSON，不要 markdown。"
)


def _s(value: Any) -> str:
    return str(value or "").strip()


def _is_placeholder(text: str) -> bool:
    return bool(PLACEHOLDER_RE.match(text.strip()))


def lint(deep: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic completeness check. Returns score 0–100 + problems."""
    problems: List[str] = []
    score = 100.0
    critical = False

    if not isinstance(deep, dict) or not deep:
        return {"score": 0.0, "passed": False, "problems": ["精读卡为空"], "critical": True}

    def penalise(points: float, msg: str, is_critical: bool = False) -> None:
        nonlocal score, critical
        score -= points
        problems.append(msg)
        critical = critical or is_critical

    for field, min_len in REQUIRED_FIELDS:
        value = _s(deep.get(field))
        if not value:
            penalise(14, f"{field} 为空", is_critical=True)
        elif _is_placeholder(value):
            penalise(10, f"{field} 只有占位符", is_critical=True)
        elif len(value) < min_len:
            penalise(6, f"{field} 过短（{len(value)} 字）")
        elif TRUNCATED_RE.search(value):
            penalise(4, f"{field} 似乎被截断")

    if not _s(deep.get("title_zh")):
        penalise(4, "缺少中文标题")

    if not _s(deep.get("sample_desc")):
        penalise(4, "缺少样本描述")

    findings = [f for f in (deep.get("findings") or []) if isinstance(f, dict)]
    if len(findings) < 2:
        penalise(16, f"关键证据只有 {len(findings)} 条（至少 2 条）", is_critical=True)
    evidences = []
    for i, f in enumerate(findings):
        claim, evidence = _s(f.get("claim")), _s(f.get("evidence"))
        if not claim:
            penalise(5, f"证据 {i + 1} 缺少结论")
        if not evidence:
            penalise(7, f"证据 {i + 1} 缺少数据/现象")
        elif _is_placeholder(evidence):
            penalise(5, f"证据 {i + 1} 只有「{evidence}」")
        evidences.append(evidence)
    if len(evidences) >= 2 and len(set(evidences)) == 1:
        penalise(8, "多条证据文案完全相同")

    followups = [_s(x) for x in (deep.get("followups") or []) if _s(x)]
    if len(followups) < 2:
        penalise(12, f"追问只有 {len(followups)} 条", is_critical=True)
    elif len(followups) < 3:
        penalise(5, "追问不足 3 条")
    if any(len(q) < 6 for q in followups):
        penalise(4, "有追问过短")

    limits = [_s(x) for x in (deep.get("limitations") or []) if _s(x)]
    if len(limits) < 2:
        penalise(8, f"局限只有 {len(limits)} 条")

    if _is_placeholder(_s(deep.get("effect"))):
        penalise(2, "效应量只有占位符")

    score = max(0.0, min(100.0, score))
    passed = score >= 70 and not critical
    return {"score": round(score, 1), "passed": passed, "problems": problems, "critical": critical}


def judge_prompt(paper: Dict[str, Any], deep: Dict[str, Any]) -> List[Dict[str, str]]:
    card = {k: deep.get(k) for k in (
        "title_zh", "one_sentence", "question", "design", "sample_desc", "findings",
        "effect", "relation", "why", "limitations", "transferable", "followups",
    )}
    user = f"""论文标题：{paper.get('title')}
期刊：{paper.get('journal')}｜{paper.get('date')}

摘要（唯一事实来源）：
{paper.get('abstract', '')[:2800]}

AI 写的精读卡：
{json.dumps(card, ensure_ascii=False, indent=1)}

逐项判断后只输出：
{{"complete": true/false, "faithful": true/false, "specific": true/false,
  "score": 0-100, "problems": ["最关键的 1-3 个问题，没有就空数组"]}}

判定标准：
- complete：六个字段（一句话/问题/设计/与我的关系/为什么读/可迁移）都有实质内容，证据≥2 条，追问=3 条。
- faithful：卡片里的数字、分组、结论都能在摘要里找到依据；出现摘要没有的数字即 false。
- specific：写到了分组、样本量、效应量或机制，而不是“具有重要意义”。
- score < 70 视为不通过。"""
    return [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}]


def judge(client: AgnesLLM, paper: Dict[str, Any], deep: Dict[str, Any]) -> Dict[str, Any]:
    data = client.chat_json(judge_prompt(paper, deep), max_tokens=900)
    if not isinstance(data, dict):
        raise LLMError("judge returned non-object")
    problems = [str(p)[:160] for p in (data.get("problems") or []) if str(p).strip()][:3]
    try:
        score = float(data.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    complete = bool(data.get("complete"))
    faithful = bool(data.get("faithful"))
    return {
        "score": max(0.0, min(100.0, score)),
        "passed": score >= 70 and complete and faithful,
        "problems": problems,
        "complete": complete,
        "faithful": faithful,
        "specific": bool(data.get("specific")),
    }


def ensure(
    deep: Optional[Dict[str, Any]],
    paper: Dict[str, Any],
    profile: Dict[str, Any],
    *,
    judge_client: Optional[AgnesLLM] = None,
    repair_client: Optional[AgnesLLM] = None,
    primary_client: Optional[AgnesLLM] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Lint → judge → repair once. Returns (best_deep, quality_record)."""
    from . import analyze  # local import avoids a cycle at module load

    qcfg = (profile.get("quality") or {})
    min_score = float(qcfg.get("min_score", 70) or 70)

    def run_judge(card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not judge_client or not judge_client.enabled:
            return None
        try:
            return judge(judge_client, paper, card)
        except Exception as exc:  # noqa: BLE001 - a judge failure must not kill the run
            print(f"[quality] judge failed: {exc}")
            return None

    lint_result = lint(deep)
    judged = run_judge(deep) if deep else None
    passed = lint_result["passed"] and (judged is None or judged["passed"])
    problems = list(lint_result["problems"]) + (judged["problems"] if judged else [])

    repaired_by = ""
    attempts = 0
    best = deep
    best_score = lint_result["score"] + (judged["score"] if judged else 0)

    target = repair_client if (repair_client and repair_client.enabled) else primary_client
    if not passed and target is not None and target.enabled and attempts < int(qcfg.get("max_repairs", 1)):
        attempts += 1
        try:
            candidate = analyze.deep_read(target, profile, paper, issues=problems[:6])
            cand_lint = lint(candidate)
            cand_judged = run_judge(candidate) if candidate else None
            cand_passed = cand_lint["passed"] and (cand_judged is None or cand_judged["passed"])
            cand_total = cand_lint["score"] + (cand_judged["score"] if cand_judged else 0)
            if cand_total >= best_score or cand_passed:
                best, best_score = candidate, cand_total
                judged = cand_judged
                lint_result = cand_lint
                passed = cand_passed
                problems = list(cand_lint["problems"]) + (cand_judged["problems"] if cand_judged else [])
                repaired_by = f"{target.model}"
        except Exception as exc:  # noqa: BLE001
            print(f"[quality] repair failed: {exc}")

    if not isinstance(best, dict):
        best = None

    record = {
        "passed": bool(passed),
        "score": lint_result["score"],
        "judge_score": round(judged["score"], 1) if judged else None,
        "problems": problems[:6],
        "repaired_by": repaired_by,
        "attempts": attempts,
    }
    if best is not None:
        best["quality"] = record
    return best, record


# ---------------------------------------------------------------- clients
def make_client(section: Dict[str, Any], default_env: str = "OPENCODE_API_KEY") -> Optional[AgnesLLM]:
    """Build a client from a quality.{judge,repair} config block."""
    if not section or not section.get("enabled", True):
        return None
    key = os.environ.get(str(section.get("api_key_env") or default_env), "").strip()
    if not key:
        return None
    return AgnesLLM(
        api_key=key,
        base_url=str(section.get("base_url") or "https://opencode.ai/inference/go/openai/v1"),
        model=str(section.get("model") or "mimo-v2.6-flash"),
        temperature=float(section.get("temperature", 0.1)),
        timeout=int(section.get("timeout", 120)),
        user_agent="daily-dental-digest/2.0 (GitHub Actions)",
    )


def make_judge(profile: Dict[str, Any]) -> Optional[AgnesLLM]:
    return make_client((profile.get("quality") or {}).get("judge") or {})


def make_repair(profile: Dict[str, Any]) -> Optional[AgnesLLM]:
    return make_client((profile.get("quality") or {}).get("repair") or {})
