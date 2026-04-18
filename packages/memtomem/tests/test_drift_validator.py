"""Tests for tools/retrieval-eval/drift_validator.py.

The validator lives in `tools/` (not the `memtomem` package), so tests
load it via `importlib.util` and exercise public functions directly.

Rule coverage: one positive + one negative case per rule, plus a
corpus-wide sanity test that the curated 6-topic corpus passes with
zero forbidden-tier violations.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from textwrap import dedent
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VALIDATOR_PATH = _REPO_ROOT / "tools" / "retrieval-eval" / "drift_validator.py"


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("drift_validator", _VALIDATOR_PATH)
    assert spec and spec.loader, f"cannot load {_VALIDATOR_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["drift_validator"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def validator() -> ModuleType:
    return _load_validator()


def _write_fixture(
    tmp_path: Path,
    body: str,
    *,
    lang: str = "ko",
    topic: str = "k8s",
    genre: str = "runbook",
) -> Path:
    target = tmp_path / "corpus_v2" / lang / topic / f"{genre}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


# ---- parser ----


def test_parse_extracts_primary_secondary_and_path_metadata(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            > Synthetic.

            ## HPA scaling

            <!-- primary: k8s/scaling -->
            <!-- secondary: observability/metrics -->

            kubectl autoscale deployment api --cpu-percent=70.

            ## PVC expansion

            <!-- primary: k8s/storage -->
            <!-- secondary: -->

            kubectl edit pvc mysql-data -n prod.
            """
        ).strip(),
        lang="ko",
        topic="k8s",
        genre="runbook",
    )
    chunks = validator.parse_fixture(path)
    assert len(chunks) == 2
    assert chunks[0].primary == "k8s/scaling"
    assert chunks[0].secondary == ("observability/metrics",)
    assert chunks[1].primary == "k8s/storage"
    assert chunks[1].secondary == ()
    assert chunks[0].lang == "ko"
    assert chunks[0].topic == "k8s"
    assert chunks[0].genre == "runbook"
    assert "kubectl autoscale" in chunks[0].body


def test_parse_skips_headings_without_metadata(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## File-level heading without metadata

            Just prose, no metadata.

            ## Real chunk

            <!-- primary: k8s/rollout -->
            <!-- secondary: -->

            kubectl rollout status deployment/api.
            """
        ).strip(),
    )
    chunks = validator.parse_fixture(path)
    assert len(chunks) == 1
    assert chunks[0].heading == "Real chunk"


def test_parse_handles_multiple_secondary_tags(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## Heading

            <!-- primary: k8s/scaling -->
            <!-- secondary: observability/metrics, cost_optimization/compute -->

            Body.
            """
        ).strip(),
    )
    chunks = validator.parse_fixture(path)
    assert chunks[0].secondary == ("observability/metrics", "cost_optimization/compute")


# ---- closed-vocab enforcement ----


def test_closed_vocab_unknown_topic_is_forbidden(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## H

            <!-- primary: nonexistent/foo -->
            <!-- secondary: -->

            body
            """
        ).strip(),
    )
    violations = validator.validate_fixture(path)
    assert any(v.rule_id == "closed-vocab-topic" and v.tier == "forbidden" for v in violations)


def test_closed_vocab_unknown_subtopic_is_forbidden(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## H

            <!-- primary: k8s/widget -->
            <!-- secondary: -->

            body
            """
        ).strip(),
    )
    violations = validator.validate_fixture(path)
    assert any(v.rule_id == "closed-vocab-subtopic" and v.tier == "forbidden" for v in violations)


def test_closed_vocab_accepts_all_15_topics(validator):
    # Sanity: closed vocab is correctly populated; no subtopic drift
    # between validator constants and design doc.
    assert set(validator.CLOSED_VOCAB.keys()) == {
        "caching",
        "postgres",
        "k8s",
        "observability",
        "ci_cd",
        "auth",
        "kafka",
        "search",
        "networking",
        "security",
        "ml_ops",
        "data_pipelines",
        "cost_optimization",
        "incident_response",
        "api_design",
    }
    for topic, subs in validator.CLOSED_VOCAB.items():
        assert len(subs) >= 5, f"{topic} has fewer than 5 subtopics"


# ---- forbidden rule: postmortem genre ≠ IR/postmortem subtopic ----


def test_forbidden_postmortem_genre_with_ir_postmortem_subtopic(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## CoreDNS outage

            <!-- primary: k8s/networking -->
            <!-- secondary: incident_response/postmortem -->

            CoreDNS ConfigMap error caused cascading DNS failures.
            """
        ).strip(),
        genre="postmortem",
    )
    violations = validator.validate_fixture(path)
    matches = [v for v in violations if v.rule_id == "genre-postmortem-vs-ir-postmortem-subtopic"]
    assert len(matches) == 1
    assert matches[0].tier == "forbidden"


def test_forbidden_rule_allows_ir_primary(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## Process improvement after outage

            <!-- primary: incident_response/mitigation -->
            <!-- secondary: incident_response/postmortem -->

            After the outage we revised our RCA template and blameless review process.
            """
        ).strip(),
        genre="postmortem",
    )
    violations = validator.validate_fixture(path)
    assert not any(v.rule_id == "genre-postmortem-vs-ir-postmortem-subtopic" for v in violations)


def test_forbidden_rule_does_not_fire_on_non_postmortem_genre(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## H

            <!-- primary: k8s/networking -->
            <!-- secondary: incident_response/postmortem -->

            body
            """
        ).strip(),
        genre="runbook",
    )
    violations = validator.validate_fixture(path)
    assert not any(v.rule_id == "genre-postmortem-vs-ir-postmortem-subtopic" for v in violations)


# ---- manual-review: kubectl logs ≠ observability/logging ----


def test_manual_review_kubectl_logs_with_obs_logging_secondary(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## 504 upstream timeout diagnosis

            <!-- primary: k8s/networking -->
            <!-- secondary: observability/logging -->

            Run `kubectl logs -n ingress-nginx` to diagnose 504 upstream timeouts.
            """
        ).strip(),
        genre="troubleshooting",
    )
    violations = validator.validate_fixture(path)
    matches = [
        v for v in violations if v.rule_id == "kubectl-logs-diagnostic-vs-observability-logging"
    ]
    assert len(matches) == 1
    assert matches[0].tier == "manual_review"


def test_manual_review_does_not_fire_without_kubectl_logs(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## Fluent Bit retention tuning

            <!-- primary: k8s/rollout -->
            <!-- secondary: observability/logging -->

            Adjust Fluent Bit DaemonSet Mem_Buf_Limit for retention.
            """
        ).strip(),
    )
    violations = validator.validate_fixture(path)
    assert not any(
        v.rule_id == "kubectl-logs-diagnostic-vs-observability-logging" for v in violations
    )


def test_manual_review_does_not_fire_without_obs_logging_secondary(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## Ingress diagnostic

            <!-- primary: k8s/networking -->
            <!-- secondary: -->

            Run `kubectl logs -l app.kubernetes.io/name=ingress-nginx` for errors.
            """
        ).strip(),
    )
    violations = validator.validate_fixture(path)
    assert not any(
        v.rule_id == "kubectl-logs-diagnostic-vs-observability-logging" for v in violations
    )


# ---- manual-review: security/access_control + RBAC body ----


def test_manual_review_security_access_control_with_rbac_body(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## Over-privileged RoleBinding

            <!-- primary: security/access_control -->
            <!-- secondary: -->

            A `cluster-admin` RoleBinding granted namespace-delete permission.
            """
        ).strip(),
        topic="security",
        genre="postmortem",
    )
    violations = validator.validate_fixture(path)
    assert any(
        v.rule_id == "security-access-control-primary-with-rbac-body" and v.tier == "manual_review"
        for v in violations
    )


def test_security_access_control_without_rbac_body_does_not_fire(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## Policy-as-code ABAC rollout

            <!-- primary: security/access_control -->
            <!-- secondary: -->

            Deploy OPA rego policies for ABAC decisions at API gateway layer.
            """
        ).strip(),
        topic="security",
    )
    violations = validator.validate_fixture(path)
    assert not any(
        v.rule_id == "security-access-control-primary-with-rbac-body" for v in violations
    )


# ---- manual-review: security/encryption + transport body (with suppression) ----


def test_manual_review_security_encryption_with_tls_body(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## Istio strict mTLS rollout

            <!-- primary: security/encryption -->
            <!-- secondary: -->

            Enable Istio PeerAuthentication STRICT mode cluster-wide.
            """
        ).strip(),
        topic="security",
        genre="adr",
    )
    violations = validator.validate_fixture(path)
    assert any(
        v.rule_id == "security-encryption-primary-with-transport-body" and v.tier == "manual_review"
        for v in violations
    )


def test_security_encryption_with_transport_split_secondary_suppressed(validator, tmp_path):
    # When curator has already tagged networking/tls or auth/mtls as
    # secondary, the functional split is explicit — don't flag.
    # Matches "Borderline cases preserved" in security ledger.
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## cert-manager Let's Encrypt renewal failure

            <!-- primary: security/encryption -->
            <!-- secondary: networking/tls -->

            cert-manager failed to renew Let's Encrypt certs, breaking mTLS.
            """
        ).strip(),
        topic="security",
        genre="postmortem",
    )
    violations = validator.validate_fixture(path)
    assert not any(
        v.rule_id == "security-encryption-primary-with-transport-body" for v in violations
    )


def test_security_encryption_with_at_rest_body_does_not_fire(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## KMS envelope encryption rollout

            <!-- primary: security/encryption -->
            <!-- secondary: -->

            Rotate KMS CMK for envelope-encrypted RDS snapshots.
            """
        ).strip(),
        topic="security",
    )
    violations = validator.validate_fixture(path)
    assert not any(
        v.rule_id == "security-encryption-primary-with-transport-body" for v in violations
    )


# ---- corpus sanity ----


def test_current_corpus_has_zero_forbidden_violations(validator):
    """Post-curation 6-topic corpus_v2 must have zero forbidden-tier findings.

    Guards against silent closed-vocab drift (someone edits a fixture
    tag without running the validator).
    """
    corpus_root = _REPO_ROOT / "packages" / "memtomem" / "tests" / "fixtures" / "corpus_v2"
    violations = validator.validate_corpus(corpus_root)
    forbidden = [v for v in violations if v.tier == "forbidden"]
    assert forbidden == [], (
        "Post-curation corpus has unexpected forbidden-tier violations: "
        + "; ".join(
            f"{v.chunk.file.relative_to(corpus_root)}#{v.chunk.index} [{v.rule_id}]"
            for v in forbidden
        )
    )


def test_current_corpus_manual_review_count_is_zero(validator):
    """Sanity: no unresolved manual-review flags on the curated corpus.

    The 4 manual-review rules are designed so that post-curation
    fixtures either pass them (curator handled the pattern) or have
    secondary tags that suppress the flag (e.g. networking/tls on
    security/encryption). If this count grows above 0, investigate
    before merging fixture edits.
    """
    corpus_root = _REPO_ROOT / "packages" / "memtomem" / "tests" / "fixtures" / "corpus_v2"
    violations = validator.validate_corpus(corpus_root)
    manual = [v for v in violations if v.tier == "manual_review"]
    assert manual == [], "Unexpected manual-review flags on curated corpus: " + "; ".join(
        f"{v.chunk.file.relative_to(corpus_root)}#{v.chunk.index} [{v.rule_id}]" for v in manual
    )


# ---- CLI ----


def test_cli_returns_1_on_forbidden(validator, tmp_path):
    _write_fixture(
        tmp_path,
        dedent(
            """
            ## H

            <!-- primary: bogus/foo -->
            <!-- secondary: -->

            body
            """
        ).strip(),
        lang="ko",
        topic="k8s",
    )
    rc = validator.main([str(tmp_path / "corpus_v2")])
    assert rc == 1


def test_cli_returns_0_on_clean(validator, tmp_path):
    _write_fixture(
        tmp_path,
        dedent(
            """
            ## H

            <!-- primary: k8s/scaling -->
            <!-- secondary: observability/metrics -->

            body
            """
        ).strip(),
    )
    rc = validator.main([str(tmp_path / "corpus_v2")])
    assert rc == 0


def test_cli_handles_single_file(validator, tmp_path):
    path = _write_fixture(
        tmp_path,
        dedent(
            """
            ## H

            <!-- primary: k8s/scaling -->
            <!-- secondary: -->

            body
            """
        ).strip(),
    )
    rc = validator.main([str(path)])
    assert rc == 0


def test_cli_skips_non_fixture_markdown(validator, tmp_path):
    # Place a README.md alongside the fixture; it has placeholder
    # `<!-- primary: topic/subtopic -->` text that would otherwise
    # fail closed-vocab. The corpus walker must skip it.
    _write_fixture(
        tmp_path,
        dedent(
            """
            ## H

            <!-- primary: k8s/scaling -->
            <!-- secondary: -->

            body
            """
        ).strip(),
    )
    readme = tmp_path / "corpus_v2" / "README.md"
    readme.write_text(
        dedent(
            """
            # corpus_v2

            ## Directory layout

            Each chunk is tagged `<!-- primary: topic/subtopic -->`.
            """
        ).strip(),
        encoding="utf-8",
    )
    rc = validator.main([str(tmp_path / "corpus_v2")])
    assert rc == 0
