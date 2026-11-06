"""Deterministic coarse ranking. Runs without any LLM so the pipeline never dies."""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

# Evidence ladder, weakest -> strongest. Level is also used by the UI probe.
LADDER: List[Tuple[str, str, int]] = [
    ("case_report", "病例报告", 0),
    ("in_vitro", "体外/细胞", 1),
    ("animal", "动物实验", 2),
    ("cross_sectional", "横断面", 3),
    ("review", "综述", 3),
    ("case_control", "病例对照", 4),
    ("cohort", "队列", 5),
    ("rct", "随机对照", 6),
    ("meta", "系统评价/Meta", 7),
]

DESIGN_PATTERNS: List[Tuple[str, str]] = [
    ("meta", r"\b(systematic review|meta-?analys\w*|network meta|umbrella review|scoping review)\b"),
    ("rct", r"\b(randomi[sz]ed( controlled)?( trial)?|randomly (assigned|allocated)|\bRCT\b|split-?mouth)\b"),
    ("cohort", r"\b(cohort|longitudinal|prospective|retrospective|follow-?up study|registry)\b"),
    ("case_control", r"\bcase-?control\b"),
    ("cross_sectional", r"\b(cross-?sectional|nhanes|national survey|questionnaire|survey)\b"),
    ("animal", r"\b(mice|mouse|murine|rat|rats|rabbit|rabbits|canine|dog|dogs|beagle|porcine|pig|minipig|sheep|ovine|zebrafish)\b"),
    ("in_vitro", r"\b(in vitro|cell culture|cells were|osteoblast|fibroblast|macrophage|organoid|ex vivo|bioreactor)\b"),
]

DESIGN_POINTS = {"meta": 18, "rct": 18, "cohort": 15, "case_control": 12, "cross_sectional": 10, "review": 10, "animal": 9, "in_vitro": 7, "case_report": 1, "unknown": 6}

METHOD_MARKERS = {
    "single-cell": r"single-?cell|scrna-?seq|single cell rna",
    "spatial": r"spatial transcriptom|spatial omics|spatial profiling",
    "organoid": r"organoid|organ-?on-?a-?chip|microphysiolog",
    "mendelian": r"mendelian randomi[sz]ation",
    "ml": r"machine learning|deep learning|neural network|radiomics|artificial intelligence",
    "multiomics": r"multi-?omics|proteomic|metabolomic|transcriptom|metagenom",
    "crispr": r"crispr|gene editing|knock-?in|knockout mice",
    "rct": r"randomi[sz]ed",
    "gwas": r"gwas|genome-?wide",
    "causal": r"causal inference|target trial|instrumental variable|mediation analys",
}

SIZE_RE = re.compile(
    r"(\d[\d,]{1,6})\s*(patients|participants|subjects|individuals|implants|teeth|samples|specimens|mice|rats|children|adults|cases|papers|studies|articles|records|scans|images)\b",
    re.I,
)
N_RE = re.compile(r"\bn\s*=\s*(\d[\d,]*)", re.I)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def detect_design(paper: Dict[str, Any]) -> Tuple[str, str, int]:
    """PubMed pub types outrank abstract keywords: a mouse *review* is still a review."""
    types = _norm(" ".join(paper.get("pub_types", [])))
    title = _norm(paper.get("title", ""))

    if "meta-analysis" in types or "systematic review" in types or re.search(r"\b(systematic review|meta-?analys\w*|network meta)\b", title):
        return "meta", "系统评价/Meta", DESIGN_POINTS["meta"]
    if "randomized controlled trial" in types:
        return "rct", "随机对照", DESIGN_POINTS["rct"]
    if re.search(r"\b(randomi[sz]ed( controlled)? trial|split-?mouth)\b", title):
        return "rct", "随机对照", DESIGN_POINTS["rct"]
    if "review" in types or re.search(r"\b(a |an )?(narrative |scoping |critical )?review\b", title):
        return "review", "综述", DESIGN_POINTS["review"]
    if "cohort" in types or re.search(r"\b(cohort|longitudinal)\b", title):
        return "cohort", "队列", DESIGN_POINTS["cohort"]

    text = _norm(" ".join([paper.get("title", ""), paper.get("abstract", "")]))
    for key, pattern in DESIGN_PATTERNS:
        if re.search(pattern, text, re.I):
            label = next((lbl for k, lbl, _ in LADDER if k == key), "其他")
            return key, label, DESIGN_POINTS.get(key, 6)
    return "unknown", "未标注", 6


def design_level(key: str) -> int:
    return next((lvl for k, _, lvl in LADDER if k == key), 1)


def parse_sample(paper: Dict[str, Any]) -> Tuple[Optional[int], str]:
    text = " ".join([paper.get("abstract", ""), paper.get("title", "")])
    best = None
    note = ""
    for m in SIZE_RE.finditer(text):
        try:
            n = int(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if n <= 0:
            continue
        unit = m.group(2).lower()
        if unit in ("papers", "studies", "articles"):  # review-level counts
            note = f"{n} 项研究"
            best = max(best or 0, n)
            continue
        if best is None or n > best:
            best, note = n, f"n={n} {unit}"
    if best is None:
        m = N_RE.search(text)
        if m:
            try:
                best = int(m.group(1).replace(",", ""))
                note = f"n={best}"
            except ValueError:
                pass
    return best, note


def tier_of(journal: str, tiers: Dict[str, str]) -> str:
    key = _norm(journal)
    if not key:
        return "C"
    for name, tier in tiers.items():
        if key == name or key.startswith(name) or name in key:
            return tier
    return "C"


def _keyword_hits(paper: Dict[str, Any], keywords: List[str], weights: Dict[str, float]) -> float:
    title = _norm(paper.get("title", ""))
    abstract = _norm(paper.get("abstract", ""))
    kws = _norm(" ".join(paper.get("keywords", [])))
    score = 0.0
    for kw in keywords:
        k = _norm(kw)
        if not k:
            continue
        w = weights.get(k, 1.0)
        if k in title:
            score += 3.0 * w
        elif k in kws:
            score += 2.0 * w
        elif k in abstract:
            score += 0.7 * w
    return score


def domain_scores(paper: Dict[str, Any], profile: Dict[str, Any]) -> List[Tuple[str, float]]:
    out = []
    for dom in profile.get("domains", []):
        hits = _keyword_hits(paper, dom.get("keywords", []), {})
        if hits > 0:
            out.append((dom.get("name", "其他"), hits * float(dom.get("weight", 1.0))))
    for q in profile.get("research_questions", []):
        hits = _keyword_hits(paper, q.get("keywords", []), {})
        if hits > 0:
            out.append((f"Q:{q.get('id')}", hits))
    return sorted(out, key=lambda x: x[1], reverse=True)


def heuristic(paper: Dict[str, Any], profile: Dict[str, Any], tiers: Dict[str, str], today: date) -> Dict[str, Any]:
    title = _norm(paper.get("title", ""))
    abstract = _norm(paper.get("abstract", ""))
    text = f"{title} {abstract}"

    design_key, design_label, design_pts = detect_design(paper)
    n, sample_note = parse_sample(paper)
    tier = tier_of(paper.get("journal", ""), tiers)

    # topic relevance 0..35
    domain_hits = domain_scores(paper, profile)
    primary_domain = domain_hits[0][0] if domain_hits else "其他"
    topic_raw = min(12.0, sum(h for _, h in domain_hits[:3]))
    topic = (topic_raw / 12.0) * 35.0

    # journal 0..15
    journal_pts = {"A": 15.0, "B": 10.0}.get(tier, 3.0)

    # sample adequacy 0..8
    size_pts = 0.0
    if n:
        size_pts = min(8.0, math.log10(1 + n) / 3.0 * 8.0)

    # freshness 0..8
    age = 30
    try:
        age = max(0, (today - date.fromisoformat(paper.get("date", "")[:10])).days)
    except Exception:
        pass
    fresh_pts = max(0.0, 8.0 - age)
    cited = int(paper.get("cited_by") or 0)
    fresh_pts = min(8.0, fresh_pts + min(3.0, cited * 0.5))

    # method novelty 0..8
    markers = [name for name, pat in METHOD_MARKERS.items() if re.search(pat, text, re.I)]
    method_pts = min(8.0, 2.2 * len(markers))

    # penalties
    penalty = 0.0
    hits = []
    for pat in profile.get("negative_patterns", []):
        p = _norm(pat)
        if p and p in text:
            penalty += 8.0
            hits.append(pat)
    penalty = min(25.0, penalty)

    total = topic + journal_pts + design_pts + size_pts + fresh_pts + method_pts - penalty
    total = max(0.0, min(100.0, total))

    return {
        "design": design_key,
        "design_label": design_label,
        "design_level": design_level(design_key),
        "sample_n": n,
        "sample_note": sample_note,
        "tier": tier,
        "domain": primary_domain if not primary_domain.startswith("Q:") else _domain_from_question(profile, primary_domain),
        "methods": markers,
        "penalty": round(penalty, 1),
        "penalty_hits": hits,
        "heuristic": round(total, 1),
        "breakdown": {
            "topic": round(topic, 1),
            "journal": round(journal_pts, 1),
            "design": round(design_pts, 1),
            "sample": round(size_pts, 1),
            "fresh": round(fresh_pts, 1),
            "method": round(method_pts, 1),
        },
    }


def _domain_from_question(profile: Dict[str, Any], key: str) -> str:
    qid = key.split(":", 1)[1]
    for q in profile.get("research_questions", []):
        if q.get("id") == qid:
            text = str(q.get("text", ""))
            return text[:12] + "…" if len(text) > 12 else text
    return "其他"


def attach(paper: Dict[str, Any], profile: Dict[str, Any], tiers: Dict[str, str], today: date) -> Dict[str, Any]:
    paper.update(heuristic(paper, profile, tiers, today))
    paper["journal_key"] = _norm(paper.get("journal", ""))
    paper["score"] = {"final": paper["heuristic"]}
    return paper


def select(papers: List[Dict[str, Any]], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Diversity-constrained pick: 1 deep + N scan."""
    quota = profile["quota"]
    ranked = sorted(papers, key=lambda p: p["score"]["final"], reverse=True)
    if not ranked:
        return {"must_read": None, "scan": [], "rest": []}
    top = ranked[0]["score"]["final"]
    near = [p for p in ranked if p["score"]["final"] >= top - 3 and len(p.get("abstract", "")) >= 400]
    primary = [p for p in near if p.get("design") != "meta"]
    must = (primary or near or ranked)[0]

    used_journals = {must["journal_key"]} if must else set()
    used_domains = {must["domain"]} if must else set()
    used_ids = {must["id"]} if must else set()

    scans: List[Dict[str, Any]] = []
    target = int(quota.get("scan", 3))
    floor = float(quota.get("min_scan_score", 0) or 0)
    for p in ranked:
        if len(scans) >= target:
            break
        if p["id"] in used_ids:
            continue
        if p["score"]["final"] < floor:
            break
        if p["journal_key"] in used_journals or p["domain"] in used_domains:
            continue
        scans.append(p)
        used_ids.add(p["id"])
        used_journals.add(p["journal_key"])
        used_domains.add(p["domain"])
    # relax constraints if the pool was narrow
    for p in ranked:
        if len(scans) >= target:
            break
        if p["id"] in used_ids:
            continue
        if p["score"]["final"] < floor:
            break
        scans.append(p)
        used_ids.add(p["id"])
    return {"must_read": must, "scan": scans, "rest": [p for p in ranked if p["id"] not in used_ids]}
