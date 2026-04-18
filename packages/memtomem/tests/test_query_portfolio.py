"""Tests for tools/retrieval-eval/query_portfolio.py.

Guards the 100-query portfolio against three classes of error:

1. **Counts drift from spec**: per-(lang, type) totals must match
   `EXPECTED_COUNTS` (EN 10/10/8/7/5/10, KO 10/10/10/7/3/10).
2. **Unmeasurable targets**: every query must have ≥ 1 chunk in the
   target language whose primary tag is in `query.targets`. Without
   this, recall / nDCG / MRR are undefined.
3. **Coverage gaps**: every 6-core topic appears as a primary target
   at least N times per language so calibration is not dominated by
   a single topic.

The corpus walk piggybacks on `drift_validator.parse_fixture` so the
tag-parsing logic stays in one place.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PORTFOLIO_PATH = _REPO_ROOT / "tools" / "retrieval-eval" / "query_portfolio.py"
_VALIDATOR_PATH = _REPO_ROOT / "tools" / "retrieval-eval" / "drift_validator.py"
_CORPUS_ROOT = _REPO_ROOT / "packages" / "memtomem" / "tests" / "fixtures" / "corpus_v2"

_CORE_TOPICS = {
    "caching",
    "postgres",
    "k8s",
    "observability",
    "security",
    "cost_optimization",
}


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def portfolio() -> ModuleType:
    # Load drift_validator first so parse_fixture is available.
    _load("drift_validator", _VALIDATOR_PATH)
    return _load("query_portfolio", _PORTFOLIO_PATH)


@pytest.fixture(scope="module")
def primary_tags_by_lang(portfolio) -> dict[str, set[str]]:
    """All primary tags present in the corpus, grouped by language."""
    drift_validator = sys.modules["drift_validator"]
    by_lang: dict[str, set[str]] = {"ko": set(), "en": set()}
    for fx in sorted(_CORPUS_ROOT.rglob("*.md")):
        parts = fx.parts
        if "corpus_v2" not in parts or fx.stem not in {
            "runbook",
            "postmortem",
            "adr",
            "troubleshooting",
        }:
            continue
        for chunk in drift_validator.parse_fixture(fx):
            by_lang[chunk.lang].add(chunk.primary)
    return by_lang


# ---- shape / counts ----


def test_total_query_count_is_100(portfolio):
    assert len(portfolio.QUERIES) == 100


def test_per_lang_type_counts_match_spec(portfolio):
    observed: Counter = Counter((q.lang, q.type) for q in portfolio.QUERIES)
    assert dict(observed) == portfolio.EXPECTED_COUNTS, (
        "Query distribution drifted from spec. "
        f"Observed: {dict(sorted(observed.items()))}. "
        f"Expected: {portfolio.EXPECTED_COUNTS}."
    )


def test_every_query_has_at_least_one_target(portfolio):
    bad = [q for q in portfolio.QUERIES if not q.targets]
    assert bad == [], f"queries without targets: {[q.text for q in bad]}"


def test_every_query_text_is_nonempty_and_unique(portfolio):
    texts = [q.text.strip() for q in portfolio.QUERIES]
    assert all(texts), "empty query text found"
    duplicates = [text for text, n in Counter(texts).items() if n > 1]
    assert duplicates == [], f"duplicate query texts: {duplicates}"


# ---- target-tag measurability ----


def test_every_target_tag_exists_as_primary_in_corpus_for_query_lang(
    portfolio, primary_tags_by_lang
):
    """Catches unmeasurable queries: targets must have ≥ 1 primary-matching
    chunk in the query's language. An unmeasurable target produces
    undefined recall / nDCG / MRR and silently corrupts calibration.
    """
    missing: list[tuple[str, str, str]] = []
    for q in portfolio.QUERIES:
        for tag in q.targets:
            if tag not in primary_tags_by_lang[q.lang]:
                missing.append((q.lang, q.text, tag))
    assert missing == [], (
        "Queries reference primary tags absent from their language's corpus:\n  "
        + "\n  ".join(f"[{lang}] {text!r} -> {tag}" for lang, text, tag in missing)
    )


def test_target_tag_format_is_topic_slash_subtopic(portfolio):
    bad = [(q.text, tag) for q in portfolio.QUERIES for tag in q.targets if "/" not in tag]
    assert bad == [], f"target tags must be topic/subtopic: {bad}"


# ---- coverage guards ----


def test_every_core_topic_appears_as_target_per_lang(portfolio):
    """Each of the 6 core topics (caching / postgres / k8s / observability /
    security / cost_optimization) must be referenced ≥ 3 times per
    language. Guards against a calibration run dominated by 1-2 topics.
    """
    per_lang_topic_count: dict[tuple[str, str], int] = defaultdict(int)
    for q in portfolio.QUERIES:
        topics_hit = {t.split("/", 1)[0] for t in q.targets}
        for topic in topics_hit:
            per_lang_topic_count[(q.lang, topic)] += 1

    shortfall = {
        (lang, topic): per_lang_topic_count[(lang, topic)]
        for lang in ("en", "ko")
        for topic in _CORE_TOPICS
        if per_lang_topic_count[(lang, topic)] < 3
    }
    assert shortfall == {}, f"core-topic coverage too thin (need ≥ 3 per lang): {shortfall}"


def test_multi_topic_queries_span_two_distinct_topics(portfolio):
    for q in portfolio.QUERIES:
        if q.type != "multi_topic":
            continue
        topics = {t.split("/", 1)[0] for t in q.targets}
        assert len(topics) >= 2, (
            f"multi_topic query spans only one topic: {q.text!r} -> {q.targets}"
        )


def test_genre_primary_queries_have_multiple_targets(portfolio):
    """Genre-primary queries select by anchor vocabulary across many
    primary subtopics of one topic; they should address a non-trivial
    relevant set (≥ 2 targets).
    """
    for q in portfolio.QUERIES:
        if q.type != "genre_primary":
            continue
        assert len(q.targets) >= 2, (
            f"genre_primary query has too-narrow target set: {q.text!r} -> {sorted(q.targets)}"
        )


# ---- helper API ----


def test_queries_by_lang_filter(portfolio):
    en = portfolio.queries_by(lang="en")
    ko = portfolio.queries_by(lang="ko")
    assert len(en) == 50
    assert len(ko) == 50
    assert all(q.lang == "en" for q in en)
    assert all(q.lang == "ko" for q in ko)


def test_queries_by_type_filter(portfolio):
    direct = portfolio.queries_by(type="direct")
    assert len(direct) == 20  # 10 EN + 10 KO
    assert all(q.type == "direct" for q in direct)


def test_queries_by_combined_filter(portfolio):
    en_direct = portfolio.queries_by(lang="en", type="direct")
    assert len(en_direct) == 10
    assert all(q.lang == "en" and q.type == "direct" for q in en_direct)
