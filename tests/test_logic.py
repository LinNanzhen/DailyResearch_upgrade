"""Offline tests: parsing, scoring, selection, rendering. No network needed.

Run: python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import analyze, fetch, render, score  # noqa: E402
from pipeline.llm import _extract_json  # noqa: E402
from pipeline.settings import load_profile  # noqa: E402

PUBMED_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>111</PMID>
      <Article>
        <ArticleTitle>Single-cell atlas of peri-implantitis <i>in vivo</i></ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Macrophage states remain undefined.</AbstractText>
          <AbstractText Label="RESULTS">We profiled 42 implants and found a <i>pathogenic</i> fibroblast state.</AbstractText>
        </Abstract>
        <Journal>
          <JournalIssue><PubDate><Year>2026</Year><Month>Nov</Month><Day>4</Day></PubDate><Volume>12</Volume><Issue>3</Issue></JournalIssue>
          <Title>Journal of Clinical Periodontology</Title>
        </Journal>
        <AuthorList><Author><LastName>Chen</LastName><Initials>Y</Initials></Author></AuthorList>
        <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
      </Article>
    </MedlineCitation>
    <PubmedData><ArticleIdList>
      <ArticleId IdType="doi">10.1000/ABC</ArticleId>
      <ArticleId IdType="pmc">PMC123</ArticleId>
    </ArticleIdList></PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


def fake_paper(**kw):
    base = {
        "id": "x", "pmid": "1", "doi": "", "pmcid": "", "title": "T", "abstract": "A" * 600,
        "journal": "Journal of Dental Research", "date": "2026-11-05", "authors": [],
        "pub_types": ["Journal Article"], "keywords": [], "cited_by": 0, "is_open_access": False,
        "url": "https://example.org",
    }
    base.update(kw)
    return base


class TestJsonExtraction(unittest.TestCase):
    def test_fenced_json(self):
        self.assertEqual(_extract_json("```json\n[{\"id\": \"a\"}]\n```"), [{"id": "a"}])

    def test_prose_around_object(self):
        raw = '好的，结果如下：\n{"match": 80, "note": "含 } 的花括号"}\n希望有用'
        self.assertEqual(_extract_json(raw)["match"], 80)

    def test_nested(self):
        raw = 'x {"a": [{"b": 1}], "c": {"d": 2}} y'
        self.assertEqual(_extract_json(raw), {"a": [{"b": 1}], "c": {"d": 2}})


class TestScoring(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile()
        self.tiers = {"journal of dental research": "A"}

    def test_review_type_beats_animal_keywords(self):
        p = fake_paper(
            title="Toward Sex-Specific Host Modulation Therapy",
            abstract="Reviewing mouse studies where mice develop bone loss. " * 3,
            pub_types=["Review", "Journal Article"],
        )
        key, label, pts = score.detect_design(p)
        self.assertEqual(key, "review")
        self.assertEqual(label, "综述")

    def test_rct_type(self):
        p = fake_paper(pub_types=["Randomized Controlled Trial"], title="Composite vs liner")
        self.assertEqual(score.detect_design(p)[0], "rct")

    def test_sample_size_parsing(self):
        p = fake_paper(abstract="We enrolled 1,208 patients and followed 98 implants. " * 3)
        n, note = score.parse_sample(p)
        self.assertEqual(n, 1208)
        self.assertIn("1208", note)

    def test_heuristic_prefers_matching_journal(self):
        good = score.attach(fake_paper(id="g", title="Peri-implantitis macrophage polarization", journal="Journal of Dental Research"), self.profile, self.tiers, date(2026, 11, 6))
        bad = score.attach(fake_paper(id="b", title="Fluoride and cognition in Ireland", journal="Unknown Journal"), self.profile, self.tiers, date(2026, 11, 6))
        self.assertGreater(good["heuristic"], bad["heuristic"])
        self.assertGreater(good["score"]["final"], 0)

    def test_negative_pattern_penalty(self):
        p = score.attach(fake_paper(id="n", abstract="Case report of a rare lesion. " * 20), self.profile, self.tiers, date(2026, 11, 6))
        self.assertGreater(p["penalty"], 0)


class TestSelection(unittest.TestCase):
    def test_one_deep_and_diverse_scan(self):
        profile = load_profile()
        tiers = {"journal of dental research": "A"}
        papers = []
        for i in range(8):
            p = score.attach(
                fake_paper(id=f"p{i}", title=f"Dental implant study number {i}", journal=f"Journal {i % 3}", date="2026-11-05"),
                profile, tiers, date(2026, 11, 6),
            )
            p["score"] = {"final": 90 - i}
            p["domain"] = f"D{i}"
            papers.append(p)
        picked = score.select(papers, profile)
        self.assertIsNotNone(picked["must_read"])
        self.assertEqual(len(picked["scan"]), profile["quota"]["scan"])
        journals = [p["journal"] for p in picked["scan"]]
        self.assertEqual(len(journals), len(set(journals)), "scan should not repeat a journal")

    def test_empty_pool(self):
        picked = score.select([], load_profile())
        self.assertIsNone(picked["must_read"])


class TestAnalyzeCleaning(unittest.TestCase):
    def test_clamp_and_truncate(self):
        out = analyze._clean_scores({
            "id": "a", "match": 180, "novelty": -5, "rigor": "70",
            "one_line": "x" * 100, "cluster": "", "skip": 1,
        })
        self.assertEqual(out["match"], 100.0)
        self.assertEqual(out["novelty"], 0.0)
        self.assertEqual(out["rigor"], 70.0)
        self.assertTrue(out["one_line"].endswith("…"))
        self.assertEqual(out["cluster"], "未归类")
        self.assertTrue(out["skip"])

    def test_deep_defaults(self):
        out = analyze._clean_deep({"title_zh": "标题", "findings": ["a"], "followups": ["q"], "reading_minutes": "999"})
        self.assertEqual(out["findings"][0]["claim"], "a")
        self.assertEqual(out["reading_minutes"], 40)


class TestPubmedParsing(unittest.TestCase):
    def test_parse(self):
        papers = fetch.parse_articles(PUBMED_XML)
        self.assertEqual(len(papers), 1)
        p = papers[0]
        self.assertEqual(p["pmid"], "111")
        self.assertEqual(p["doi"], "10.1000/abc")
        self.assertEqual(p["pmcid"], "PMC123")
        self.assertEqual(p["date"], "2026-11-04")
        self.assertIn("pathogenic fibroblast", p["abstract"])
        self.assertNotIn("<i>", p["title"])
        self.assertEqual(p["journal"], "Journal of Clinical Periodontology")

    def test_droppable_editorial(self):
        self.assertTrue(fetch.is_droppable({"pub_types": ["Editorial"]}))
        self.assertFalse(fetch.is_droppable({"pub_types": ["Journal Article", "Review"]}))


class TestRender(unittest.TestCase):
    def test_build_day_shape(self):
        profile = load_profile()
        must = fake_paper(id="m", title="Must")
        must["score"] = {"final": 88, "match": 90}
        must["deep"] = {"title_zh": "必读", "one_sentence": "一句话", "followups": ["q1"]}
        scan = [fake_paper(id="s", title="Scan")]
        day = render.build_day(profile, must, scan, [], {"shown": 2}, ai=True, model="m", usage={})
        self.assertEqual(day["must_read"]["title_zh"], "必读")
        self.assertEqual(len(day["scan"]), 1)
        json.dumps(day, ensure_ascii=False)  # must be serialisable

    def test_backlog_rotation(self):
        items = [{"id": "old", "date_shown": "2026-10-30", "score": 50}]
        picks = [fake_paper(id="new")]
        kept = render.update_backlog(items, picks, max_age=21, quota=3)
        ids = [i["id"] for i in kept]
        self.assertIn("old", ids)
        self.assertIn("new", ids)


if __name__ == "__main__":
    unittest.main()
