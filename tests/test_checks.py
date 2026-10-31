"""Tests for k8s_ready_check."""

import pytest

from k8s_ready_check.checks import run_all


def make_deployment(**overrides):
    container = {
        "name": "app",
        "image": "registry.example.com/app:1.2.3",
        "readinessProbe": {"httpGet": {"path": "/", "port": 8080}},
        "livenessProbe": {"httpGet": {"path": "/", "port": 8080}},
        "resources": {
            "requests": {"cpu": "100m", "memory": "128Mi"},
            "limits": {"cpu": "500m", "memory": "512Mi"},
        },
        "securityContext": {
            "runAsNonRoot": True,
            "allowPrivilegeEscalation": False,
        },
    }
    container.update(overrides.pop("container", {}))
    doc = {
        "kind": "Deployment",
        "metadata": {"name": "web"},
        "spec": {
            "replicas": 3,
            "strategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxUnavailable": 1, "maxSurge": 1},
            },
            "template": {
                "spec": {
                    "serviceAccountName": "web",
                    "terminationGracePeriodSeconds": 30,
                    "containers": [container],
                }
            },
        },
    }
    return doc


def levels(findings):
    return {f["level"] for f in findings}


def test_clean_manifest_has_no_findings():
    assert run_all(make_deployment()) == []


def test_missing_readiness_probe_is_error():
    doc = make_deployment(container={"readinessProbe": None})
    del doc["spec"]["template"]["spec"]["containers"][0]["readinessProbe"]
    findings = run_all(doc)
    assert "error" in levels(findings)
    assert any("readinessProbe" in f["message"] for f in findings)


def test_latest_tag_is_error():
    doc = make_deployment(container={"image": "app:latest"})
    findings = run_all(doc)
    assert any(
        f["level"] == "error" and f["check"] == "image-tag" for f in findings
    )


def test_missing_resources_is_error():
    doc = make_deployment()
    del doc["spec"]["template"]["spec"]["containers"][0]["resources"]
    findings = run_all(doc)
    assert any(
        f["level"] == "error" and f["check"] == "resources" for f in findings
    )


def test_single_replica_warns():
    doc = make_deployment()
    doc["spec"]["replicas"] = 1
    findings = run_all(doc)
    assert any(f["check"] == "replicas" for f in findings)


def test_privilege_escalation_warns():
    doc = make_deployment(
        container={"securityContext": {"allowPrivilegeEscalation": True}}
    )
    findings = run_all(doc)
    assert any(f["check"] == "security" for f in findings)


def test_non_deployment_skips_replica_check():
    doc = make_deployment()
    doc["kind"] = "StatefulSet"
    doc["spec"]["replicas"] = 1
    assert not any(f["check"] == "replicas" for f in run_all(doc))


def test_missing_max_unavailable_warns():
    doc = make_deployment()
    del doc["spec"]["strategy"]
    findings = run_all(doc)
    assert any(
        f["level"] == "warn" and f["check"] == "rolling-update"
        for f in findings
    )


def test_explicit_max_unavailable_passes():
    doc = make_deployment()
    doc["spec"]["strategy"]["rollingUpdate"]["maxUnavailable"] = "25%"
    assert not any(f["check"] == "rolling-update" for f in run_all(doc))


def test_invalid_max_unavailable_warns():
    doc = make_deployment()
    doc["spec"]["strategy"]["rollingUpdate"]["maxUnavailable"] = "150%"
    findings = run_all(doc)
    assert any(
        f["level"] == "warn" and f["check"] == "rolling-update"
        for f in findings
    )


def test_recreate_strategy_skips_rolling_update_check():
    doc = make_deployment()
    doc["spec"]["strategy"] = {"type": "Recreate"}
    assert not any(f["check"] == "rolling-update" for f in run_all(doc))


def test_missing_termination_grace_warns():
    doc = make_deployment()
    del doc["spec"]["template"]["spec"]["terminationGracePeriodSeconds"]
    findings = run_all(doc)
    assert any(
        f["level"] == "warn" and f["check"] == "termination-grace"
        for f in findings
    )


def test_explicit_termination_grace_passes():
    doc = make_deployment()
    doc["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] = 60
    assert not any(f["check"] == "termination-grace" for f in run_all(doc))


def test_invalid_termination_grace_warns():
    doc = make_deployment()
    doc["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] = -5
    findings = run_all(doc)
    assert any(
        f["level"] == "warn" and f["check"] == "termination-grace"
        for f in findings
    )


def test_string_termination_grace_warns():
    doc = make_deployment()
    doc["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] = "30s"
    findings = run_all(doc)
    assert any(
        f["level"] == "warn" and f["check"] == "termination-grace"
        for f in findings
    )


def test_no_template_skips_termination_grace_check():
    doc = {"kind": "Deployment", "metadata": {"name": "web"}, "spec": {}}
    assert not any(
        f["check"] == "termination-grace" for f in run_all(doc)
    )


def test_non_deployment_skips_rolling_update_check():
    doc = make_deployment()
    doc["kind"] = "StatefulSet"
    del doc["spec"]["strategy"]
    assert not any(f["check"] == "rolling-update" for f in run_all(doc))
