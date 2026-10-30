"""Tests for the --output json mode of the CLI."""

import json

import pytest

from k8s_ready_check.cli import main


CLEAN = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    metadata:
      labels: {app: web}
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: app
          image: registry.example.com/app:1.2.3
          readinessProbe:
            httpGet: {path: /, port: 8080}
          livenessProbe:
            httpGet: {path: /, port: 8080}
          resources:
            requests: {cpu: 100m, memory: 128Mi}
            limits: {cpu: 500m, memory: 512Mi}
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: web-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels: {app: web}
"""

FLOATING_TAG = CLEAN.replace(
    "registry.example.com/app:1.2.3", "registry.example.com/app:latest"
)


def write_manifest(tmp_path, content, name="deployment.yaml"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_json_clean_manifest_reports_no_findings(tmp_path, capsys):
    path = write_manifest(tmp_path, CLEAN)
    code = main([path, "--output", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["results"] == [
        {
            "file": path,
            "kind": "Deployment",
            "name": "web",
            "findings": [],
        },
        {
            "file": path,
            "kind": "PodDisruptionBudget",
            "name": "web-pdb",
            "findings": [],
        },
    ]
    assert out["summary"] == {
        "files": 1,
        "resources": 2,
        "findings": 0,
        "errors": 0,
        "warnings": 0,
    }


def test_json_finding_carries_level_check_and_message(tmp_path, capsys):
    path = write_manifest(tmp_path, FLOATING_TAG)
    code = main([path, "--output", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    findings = out["results"][0]["findings"]
    assert any(
        f["level"] == "error"
        and f["check"] == "image-tag"
        and "latest" in f["message"]
        for f in findings
    )
    assert out["summary"]["errors"] >= 1


def test_json_strict_error_exit_code_is_two(tmp_path, capsys):
    path = write_manifest(tmp_path, FLOATING_TAG)
    code = main([path, "--output", "json", "--strict"])
    json.loads(capsys.readouterr().out)
    assert code == 2


def test_json_covers_multiple_documents(tmp_path, capsys):
    path = write_manifest(tmp_path, CLEAN + "---\n" + FLOATING_TAG)
    code = main([path, "--output", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert len(out["results"]) == 4
    assert out["results"][0]["findings"] == []
    assert out["results"][1]["findings"] == []
    assert out["results"][2]["findings"]
    assert out["results"][3]["findings"] == []
    assert out["summary"]["resources"] == 4


def test_text_output_is_unchanged(tmp_path, capsys):
    path = write_manifest(tmp_path, CLEAN)
    code = main([path])
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip() == (
        f"ok   Deployment/web ({path})\n"
        f"ok   PodDisruptionBudget/web-pdb ({path})"
    )
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
