"""Print a Markdown digest for the GitHub Actions job summary."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    try:
        idx = json.loads((ROOT / "data" / "index.json").read_text(encoding="utf-8"))
    except Exception:
        print("_没有生成数据_")
        return 0
    latest = idx.get("latest")
    if not latest:
        return 0
    day = json.loads((ROOT / "data" / "daily" / f"{latest}.json").read_text(encoding="utf-8"))
    must = day.get("must_read") or {}
    print(f"## {latest} 文献日课\n")
    print(f"- 状态：{'AI 排序' if day.get('ai') else '确定性排序（未配置 AGNES_API_KEY）'}")
    print(f"- 候选 {day.get('stats', {}).get('candidates', '?')} 篇 → 留下 {(1 if must else 0) + len(day.get('scan') or [])} 篇")
    if must:
        print(f"- 精读：**{must.get('title_zh') or must.get('title')}** (`{must.get('journal')}`)")
        passed = sum(1 for m in (day.get("must_reads") or []) if ((m.get("deep") or {}).get("quality") or {}).get("passed"))
        repaired = sum(1 for m in (day.get("must_reads") or []) if ((m.get("deep") or {}).get("quality") or {}).get("repaired_by"))
        if passed or repaired:
            print(f"- 质检：{passed}/{len(day.get('must_reads') or [])} 通过，{repaired} 篇自动重写")
    for p in day.get("scan") or []:
        print(f"- 速览：{p.get('title_zh') or p.get('title')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
