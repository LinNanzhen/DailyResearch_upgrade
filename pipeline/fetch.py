"""Retrieval layer: PubMed E-utilities (fresh, daily-indexed).

Europe PMC is intentionally not used for retrieval: its FIRST_PDATE lags behind
print issues, so a 3-day window silently misses the newest papers.
"""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
TOOL = "daily-dental-digest"
EMAIL = "linnanzhen@users.noreply.github.com"

DROP_TYPES = {
    "editorial", "comment", "letter", "news", "published erratum", "erratum",
    "retraction of publication", "retracted publication", "congress",
    "case reports", "clinical conference", "biography", "interview", "address",
    "book review", "preprint", "overall", "retraction notice",
}

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

TAG_RE = re.compile(r"<[^>]+>")

_session = requests.Session()
_session.headers.update({"User-Agent": f"{TOOL}/1.0 (mailto:{EMAIL})"})
_last_call = [0.0]


def _throttle(min_interval: float = 0.36) -> None:
    delta = time.time() - _last_call[0]
    if delta < min_interval:
        time.sleep(min_interval - delta)
    _last_call[0] = time.time()


def _get(url: str, params: Dict[str, Any], tries: int = 4) -> requests.Response:
    last: Optional[Exception] = None
    for i in range(tries):
        _throttle()
        try:
            resp = _session.get(url, params=params, timeout=40)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.2 * (i + 1))
    raise RuntimeError(f"PubMed request failed: {last}")


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def build_term(journals: List[str], start: date, end: date) -> str:
    jparts = " OR ".join(f'"{j}"[Journal]' for j in journals)
    window = f'("{start:%Y/%m/%d}"[Date - Publication] : "{end:%Y/%m/%d}"[Date - Publication])'
    return f"({jparts}) AND {window}"


def _parse_date(article: ET.Element) -> str:
    node = article.find(".//ArticleDate")
    if node is None:
        node = article.find(".//JournalIssue/PubDate")
    if node is None:
        return ""
    year = node.findtext("Year") or ""
    month = node.findtext("Month") or ""
    day = node.findtext("Day") or "1"
    if not year:
        medline = node.findtext("MedlineDate") or ""
        m = re.search(r"(\d{4})", medline)
        year = m.group(1) if m else ""
        mm = re.search(r"([A-Za-z]{3})", medline)
        month = mm.group(1) if mm else "1"
    if not year:
        return ""
    if month.isdigit():
        mon = int(month)
    else:
        mon = MONTHS.get(month[:3].lower(), 1)
    try:
        return date(int(year), mon, int(re.sub(r"\D", "", day) or 1)).isoformat()
    except ValueError:
        return f"{year}-{mon:02d}-01"


def _authors(article: ET.Element) -> List[str]:
    out = []
    for a in article.findall(".//AuthorList/Author"):
        last = a.findtext("LastName") or ""
        initials = a.findtext("Initials") or a.findtext("ForeName") or ""
        collective = a.findtext("CollectiveName") or ""
        name = f"{last} {initials}".strip() or collective
        if name:
            out.append(name)
    return out[:12]


def _abstract(article: ET.Element) -> str:
    parts = []
    for node in article.findall(".//Abstract/AbstractText"):
        label = node.get("Label") or ""
        body = _clean("".join(node.itertext()))
        if body:
            parts.append(f"{label}: {body}" if label else body)
    return " ".join(parts)


def parse_articles(xml_text: str) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_text)
    papers: List[Dict[str, Any]] = []
    for art in root.findall(".//PubmedArticle"):
        pmid = art.findtext(".//PMID") or ""
        title_node = art.find(".//ArticleTitle")
        title = _clean("".join(title_node.itertext())) if title_node is not None else ""
        journal = art.findtext(".//Journal/Title") or art.findtext(".//MedlineJournalInfo/MedlineTA") or ""
        doi = ""
        for el in art.findall(".//ELocationID"):
            if (el.get("EIdType") or "").lower() == "doi" and el.text:
                doi = el.text.strip().lower()
                break
        if not doi:
            for aid in art.findall(".//ArticleIdList/ArticleId"):
                if (aid.get("IdType") or "").lower() == "doi" and aid.text:
                    doi = aid.text.strip().lower()
                    break
        pmc = ""
        for aid in art.findall(".//ArticleIdList/ArticleId"):
            if (aid.get("IdType") or "").lower() == "pmc" and aid.text:
                pmc = aid.text.strip()
                break
        pub_types = [(_clean(t.text) or "") for t in art.findall(".//PublicationTypeList/PublicationType")]
        keywords = [_clean(k.text) for k in art.findall(".//KeywordList/Keyword")]
        mesh = [(_clean(m.findtext("DescriptorName")) or "") for m in art.findall(".//MeshHeading")]
        volume = art.findtext(".//JournalIssue/Volume") or ""
        issue = art.findtext(".//JournalIssue/Issue") or ""
        pages = art.findtext(".//Pagination/MedlinePgn") or ""
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        papers.append({
            "id": doi or f"pmid:{pmid}",
            "source": "pubmed",
            "pmid": pmid,
            "doi": doi,
            "pmcid": pmc,
            "title": title.rstrip("."),
            "abstract": _abstract(art),
            "journal": journal,
            "date": _parse_date(art),
            "authors": _authors(art),
            "pub_types": [p for p in pub_types if p],
            "keywords": [k for k in keywords if k] or [m for m in mesh if m][:10],
            "volume": volume,
            "issue": issue,
            "pages": pages,
            "cited_by": 0,
            "is_open_access": bool(pmc),
            "url": url,
        })
    return papers


def is_droppable(paper: Dict[str, Any]) -> bool:
    types = {t.lower() for t in paper.get("pub_types", [])}
    return bool(types & DROP_TYPES)


def search_ids(term: str, retmax: int = 500) -> List[str]:
    resp = _get(ESEARCH, {
        "db": "pubmed", "term": term, "retmax": retmax,
        "retmode": "json", "sort": "pub_date", "tool": TOOL, "email": EMAIL,
    })
    data = resp.json()
    return list((data.get("esearchresult") or {}).get("idlist") or [])


def fetch_details(ids: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i in range(0, len(ids), 150):
        batch = ids[i : i + 150]
        resp = _get(EFETCH, {
            "db": "pubmed", "id": ",".join(batch), "retmode": "xml",
            "tool": TOOL, "email": EMAIL,
        })
        try:
            out.extend(parse_articles(resp.text))
        except ET.ParseError as exc:
            print(f"[fetch] XML parse failed for batch starting {batch[0]}: {exc}")
    return out


def fetch_all(profile: Dict[str, Any], start: date, end: date, max_raw: int = 500) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    stats = {"queries": 0, "ids": 0, "raw": 0, "dropped_type": 0, "no_abstract": 0, "query_errors": 0}
    journals = list(profile["sources"]["journals"].get("tier_a", [])) + list(profile["sources"]["journals"].get("tier_b", []))
    terms = []
    if journals:
        terms.append(build_term(journals, start, end))
    for tpl in profile["sources"].get("topic_queries", []):
        q = str(tpl)
        if "{window}" in q:
            q = q.replace("{window}", f'("{start:%Y/%m/%d}"[Date - Publication] : "{end:%Y/%m/%d}"[Date - Publication])')
        terms.append(q)

    ids: List[str] = []
    for term in terms:
        try:
            found = search_ids(term)
            ids.extend(found)
            stats["queries"] += 1
            stats["ids"] += len(found)
            print(f"[fetch] query ok: +{len(found)} ids :: {term[:80]}")
        except Exception as exc:  # noqa: BLE001
            stats["query_errors"] += 1
            print(f"[fetch] query failed: {exc} :: {term[:100]}")

    uniq: List[str] = []
    seen_ids = set()
    for pid in ids:
        if pid not in seen_ids:
            seen_ids.add(pid)
            uniq.append(pid)
    if len(uniq) > max_raw:
        uniq = uniq[:max_raw]

    papers = fetch_details(uniq)
    stats["raw"] = len(papers)

    out: Dict[str, Dict[str, Any]] = {}
    for paper in papers:
        if not paper["title"] or is_droppable(paper):
            stats["dropped_type"] += 1
            continue
        if len(paper["abstract"]) < 200:
            stats["no_abstract"] += 1
            continue
        key = paper["id"]
        if key not in out:
            out[key] = paper
    return list(out.values()), stats


def default_window(days: int) -> Tuple[date, date]:
    end = date.today()
    return end - timedelta(days=days), end
