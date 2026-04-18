#!/usr/bin/env python3
"""B.2 v2 drift validator — CI guard for corpus_v2 fixtures.

Three-tier rule set derived from the 6-topic curation ledger
(caching baseline + postgres + cost_optimization + security +
observability + k8s). See `docs/planning/b2-v2-design.md`
§ "Drift validator" and `docs/planning/b2-v2-phase2b-ledger.md`
§ "Deferred decisions" for rule derivation.

Tiers:
- **forbidden** (auto-reject): closed-vocab violations + systematic
  patterns with ≥ 3 observed events across topics and no documented
  valid counter-example.
- **manual_review** (warn, don't block): patterns where a rule fires
  on content that may be legitimate depending on body context;
  curator verifies per chunk.

Usage:
    uv run python tools/retrieval-eval/drift_validator.py \\
        packages/memtomem/tests/fixtures/corpus_v2
    # Exit code 1 if any forbidden-tier violation found; 0 otherwise.

Both a single fixture file and a corpus root are accepted.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Closed vocabulary: 15 topics × 5 subtopics, frozen 2026-04-17.
# Mirrors docs/planning/b2-v2-design.md § "Seed subtopics".
CLOSED_VOCAB: dict[str, frozenset[str]] = {
    "caching": frozenset({"redis", "eviction", "invalidation", "stampede", "replication"}),
    "postgres": frozenset({"indexing", "replication", "vacuum", "connection_pool", "partitioning"}),
    "k8s": frozenset({"scheduling", "networking", "storage", "scaling", "rollout"}),
    "observability": frozenset({"metrics", "logging", "tracing", "alerting", "synthetic"}),
    "ci_cd": frozenset({"pipeline", "caching", "deployment", "testing", "release"}),
    "auth": frozenset({"oauth", "jwt", "mtls", "rbac", "session", "webauthn"}),
    "kafka": frozenset({"producer", "consumer", "topic", "connect", "streams"}),
    "search": frozenset({"indexing", "query", "relevance", "cluster", "ingestion"}),
    "networking": frozenset({"dns", "load_balancing", "tls", "service_mesh", "connection_pool"}),
    "security": frozenset({"vulnerability", "secrets", "encryption", "access_control", "incident"}),
    "ml_ops": frozenset({"training", "serving", "monitoring", "feature_store", "versioning"}),
    "data_pipelines": frozenset(
        {"ingestion", "transformation", "orchestration", "quality", "warehouse"}
    ),
    "cost_optimization": frozenset({"compute", "storage", "network", "database", "observability"}),
    "incident_response": frozenset(
        {"detection", "mitigation", "communication", "postmortem", "oncall"}
    ),
    "api_design": frozenset({"rest", "grpc", "rate_limiting", "pagination", "idempotency"}),
}


@dataclass(frozen=True)
class Chunk:
    file: Path
    index: int
    heading: str
    primary: str
    secondary: tuple[str, ...]
    body: str
    genre: str
    topic: str
    lang: str


@dataclass(frozen=True)
class Violation:
    chunk: Chunk
    rule_id: str
    tier: str
    message: str


@dataclass(frozen=True)
class Rule:
    id: str
    tier: str
    rationale: str
    check: Callable[[Chunk], bool]


def _body_mentions(body: str, keywords: list[str]) -> bool:
    lower = body.lower()
    return any(kw.lower() in lower for kw in keywords)


# ---- rule set (derived from 6-topic curation ledger, locked 2026-04-18) ----

RULES: list[Rule] = [
    # Forbidden — Pattern 2 (k8s ledger, 3 events: B7 #1, B7 #2, B8 #2).
    # The `postmortem` genre axis must not be conflated with the
    # `incident_response/postmortem` subtopic (IR process: RCA template,
    # blameless culture, action-item tracking). A k8s postmortem ABOUT
    # a k8s outage is genre=postmortem but subtopic-wise is k8s/*, not
    # IR process.
    Rule(
        id="genre-postmortem-vs-ir-postmortem-subtopic",
        tier="forbidden",
        rationale=(
            "Postmortem-genre chunk with non-IR primary cannot tag "
            "incident_response/postmortem as secondary. That subtopic refers "
            "to the IR *process* (RCA template, blameless culture), not to "
            "the genre axis of writing a postmortem. "
            "Source: k8s ledger Pattern 2 (3 events)."
        ),
        check=lambda c: (
            c.genre == "postmortem"
            and not c.primary.startswith("incident_response/")
            and "incident_response/postmortem" in c.secondary
        ),
    ),
    # Manual-review — Pattern 1 (k8s ledger, 3 events: B3 #2, B5 #1, B6 #2).
    # `kubectl logs` as a diagnostic tool ≠ logging-pipeline subtopic.
    # Flag so the curator verifies body genuinely discusses logging
    # pipelines (Fluent Bit, Loki, retention, log-level tuning).
    Rule(
        id="kubectl-logs-diagnostic-vs-observability-logging",
        tier="manual_review",
        rationale=(
            "k8s/* primary + observability/logging secondary + body uses "
            "`kubectl logs` as diagnostic tool. Verify body genuinely "
            "discusses the logging pipeline (Fluent Bit, Loki, retention, "
            "log-level tuning). `kubectl logs <pod>` alone is diagnostic. "
            "Source: k8s ledger Pattern 1 (3 events)."
        ),
        check=lambda c: (
            c.primary.startswith("k8s/")
            and "observability/logging" in c.secondary
            and "kubectl logs" in c.body.lower()
        ),
    ),
    # Manual-review — security ledger reclassifications (2 events:
    # trouble KO #1, postmortem KO #2). security/access_control primary
    # with RBAC-specific body (Role/RoleBinding/ClusterRoleBinding)
    # reclassifies to auth/rbac primary.
    Rule(
        id="security-access-control-primary-with-rbac-body",
        tier="manual_review",
        rationale=(
            "security/access_control primary + body mentions RBAC-specific "
            "resources (Role, RoleBinding, ClusterRoleBinding). RBAC content "
            "typically reclassifies to auth/rbac primary. "
            "Source: security ledger (trouble KO #1, postmortem KO #2)."
        ),
        check=lambda c: (
            c.primary == "security/access_control"
            and _body_mentions(c.body, ["rbac", "rolebinding", "clusterrolebinding"])
        ),
    ),
    # Manual-review — security ledger reclassifications (3 events:
    # adr EN #1, runbook KO #2, trouble KO #2). security/encryption
    # primary with transport-layer body (TLS, mTLS, cert-manager,
    # certbot, PeerAuthentication) reclassifies to networking/tls or
    # auth/mtls. security/encryption is at-rest encryption.
    #
    # Suppressed if the curator has already tagged `networking/tls`
    # or `auth/mtls` as secondary — in that case the functional split
    # is explicit and the flag would be redundant. Matches the
    # "Borderline cases preserved" precedent (security ledger
    # postmortem EN #3, runbook EN #1).
    Rule(
        id="security-encryption-primary-with-transport-body",
        tier="manual_review",
        rationale=(
            "security/encryption primary + body mentions transport-layer "
            "encryption (TLS, mTLS, cert-manager, certbot, PeerAuthentication) "
            "and secondary does not already capture the transport split "
            "(networking/tls or auth/mtls). Reclassify primary or add the "
            "transport-split secondary. "
            "Source: security ledger (adr EN #1, runbook KO #2, trouble KO #2)."
        ),
        check=lambda c: (
            c.primary == "security/encryption"
            and _body_mentions(
                c.body,
                ["tls", "mtls", "cert-manager", "certbot", "peerauthentication"],
            )
            and "networking/tls" not in c.secondary
            and "auth/mtls" not in c.secondary
        ),
    ),
]


# ---- parser ----

_HEADING_RE = re.compile(r"^## (?P<heading>.+)$", re.MULTILINE)
_PRIMARY_RE = re.compile(r"<!--\s*primary:\s*(?P<value>\S+)\s*-->")
_SECONDARY_RE = re.compile(r"<!--\s*secondary:\s*(?P<value>[^\n]*?)\s*-->")


def _parse_path_metadata(path: Path) -> tuple[str, str, str]:
    """Extract (lang, topic, genre) from corpus_v2 fixture path.

    Path convention: .../corpus_v2/<lang>/<topic>/<genre>.md
    """
    genre = path.stem
    parts = path.parts
    try:
        corpus_idx = parts.index("corpus_v2")
        lang = parts[corpus_idx + 1]
        topic = parts[corpus_idx + 2]
    except (ValueError, IndexError):
        lang = "?"
        topic = "?"
    return lang, topic, genre


def parse_fixture(path: Path) -> list[Chunk]:
    """Parse a corpus_v2 fixture file into Chunks.

    Only headings followed by a `<!-- primary: ... -->` metadata tag
    are considered chunks. Headings without metadata (e.g. file
    disclaimer) are skipped.
    """
    text = path.read_text(encoding="utf-8")
    lang, topic, genre = _parse_path_metadata(path)

    headings = list(_HEADING_RE.finditer(text))
    chunks: list[Chunk] = []
    for i, match in enumerate(headings):
        start = match.start()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        block = text[start:end]
        primary_m = _PRIMARY_RE.search(block)
        if not primary_m:
            continue
        secondary_m = _SECONDARY_RE.search(block)
        primary = primary_m.group("value").strip()
        sec_raw = secondary_m.group("value").strip() if secondary_m else ""
        secondary = tuple(s.strip() for s in sec_raw.split(",") if s.strip())
        metadata_end = (secondary_m or primary_m).end()
        body = block[metadata_end:].strip()

        chunks.append(
            Chunk(
                file=path,
                index=i,
                heading=match.group("heading").strip(),
                primary=primary,
                secondary=secondary,
                body=body,
                genre=genre,
                topic=topic,
                lang=lang,
            )
        )
    return chunks


# ---- validation ----


def _check_closed_vocab(chunk: Chunk) -> list[Violation]:
    violations: list[Violation] = []
    for tag in (chunk.primary, *chunk.secondary):
        if "/" not in tag:
            violations.append(
                Violation(
                    chunk=chunk,
                    rule_id="closed-vocab-format",
                    tier="forbidden",
                    message=f"Tag '{tag}' is not in topic/subtopic format.",
                )
            )
            continue
        topic, sub = tag.split("/", 1)
        if topic not in CLOSED_VOCAB:
            violations.append(
                Violation(
                    chunk=chunk,
                    rule_id="closed-vocab-topic",
                    tier="forbidden",
                    message=(
                        f"Tag '{tag}' uses unknown topic '{topic}' "
                        "(not in 15-topic closed vocabulary)."
                    ),
                )
            )
        elif sub not in CLOSED_VOCAB[topic]:
            violations.append(
                Violation(
                    chunk=chunk,
                    rule_id="closed-vocab-subtopic",
                    tier="forbidden",
                    message=(
                        f"Tag '{tag}' uses unknown subtopic; "
                        f"topic '{topic}' allows {sorted(CLOSED_VOCAB[topic])}."
                    ),
                )
            )
    return violations


def validate_chunk(chunk: Chunk) -> list[Violation]:
    violations = _check_closed_vocab(chunk)
    for rule in RULES:
        if rule.check(chunk):
            violations.append(
                Violation(
                    chunk=chunk,
                    rule_id=rule.id,
                    tier=rule.tier,
                    message=rule.rationale,
                )
            )
    return violations


def validate_fixture(path: Path) -> list[Violation]:
    violations: list[Violation] = []
    for chunk in parse_fixture(path):
        violations.extend(validate_chunk(chunk))
    return violations


_GENRE_STEMS = {"runbook", "postmortem", "adr", "troubleshooting"}


def _is_fixture_path(path: Path) -> bool:
    """True if path is a corpus_v2 genre fixture (not README / other)."""
    if path.suffix != ".md" or path.stem not in _GENRE_STEMS:
        return False
    parts = path.parts
    try:
        corpus_idx = parts.index("corpus_v2")
    except ValueError:
        return False
    # .../corpus_v2/<lang>/<topic>/<genre>.md  →  genre is len-1 after corpus_v2
    return len(parts) - corpus_idx - 1 == 3


def validate_corpus(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for fixture in sorted(root.rglob("*.md")):
        if not _is_fixture_path(fixture):
            continue
        violations.extend(validate_fixture(fixture))
    return violations


# ---- CLI ----


def _format_violation(v: Violation, root: Path | None) -> str:
    rel = v.chunk.file
    try:
        rel = v.chunk.file.relative_to(root) if root else v.chunk.file
    except ValueError:
        rel = v.chunk.file
    return (
        f"  {rel}#{v.chunk.index} [{v.chunk.primary}] {v.chunk.heading!r}\n"
        f"    rule: {v.rule_id}\n"
        f"    {v.message}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "target",
        type=Path,
        help="corpus_v2 root directory, topic directory, or a single fixture .md",
    )
    args = parser.parse_args(argv)

    target: Path = args.target
    if target.is_file():
        violations = validate_fixture(target)
        display_root: Path | None = target.parent
    elif target.is_dir():
        violations = validate_corpus(target)
        display_root = target
    else:
        print(f"error: {target} is not a file or directory", file=sys.stderr)
        return 2

    forbidden = [v for v in violations if v.tier == "forbidden"]
    manual = [v for v in violations if v.tier == "manual_review"]

    if forbidden:
        print(f"FORBIDDEN ({len(forbidden)}):")
        for v in forbidden:
            print(_format_violation(v, display_root))
    if manual:
        print(f"MANUAL-REVIEW ({len(manual)}):")
        for v in manual:
            print(_format_violation(v, display_root))
    if not violations:
        print(f"OK: no violations in {target}")

    return 1 if forbidden else 0


if __name__ == "__main__":
    raise SystemExit(main())
