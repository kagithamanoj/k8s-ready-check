"""Tests for the --ignore flag and the run_all ignore parameter."""

import json

import pytest
import yaml

from k8s_ready_check.checks import CHECK_NAMES, run_all
from k8s_ready_check.cli import main


MANIFEST = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  template:
    spec:
      serviceAccountName: web
      terminationGracePeriodSeconds: 30
      containers:
        - name: app
          image: registry.example.com/app:latest
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
"""


def load_doc():
    return yaml.safe_load(MANIFEST)


def check_names(findings):
    return {f["check"] for f in findings}


def write_manifest(tmp_path, content, name="deployment.yaml"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_ignore_drops_only_the_named_check():
    findings = run_all(load_doc(), pdbs=[], ignore={"image-tag"})
    assert "image-tag" not in check_names(findings)
    assert check_names(findings) == {
        "rolling-update",
        "replicas",
        "pod-disruption-budget",
    }


def test_ignore_pod_disruption_budget():
    findings = run_all(
        load_doc(), pdbs=[], ignore={"pod-disruption-budget"}
    )
    assert "pod-disruption-budget" not in check_names(findings)
    assert "image-tag" in check_names(findings)


def test_ignore_empty_and_none_keep_all_findings():
    base = run_all(load_doc(), pdbs=[])
    assert run_all(load_doc(), pdbs=[], ignore=set()) == base
    assert run_all(load_doc(), pdbs=[], ignore=None) == base


def test_check_names_covers_every_emitted_check():
    assert len(CHECK_NAMES) == len(set(CHECK_NAMES))
    findings = run_all(load_doc(), pdbs=[])
    assert check_names(findings) <= set(CHECK_NAMES)


def test_cli_ignore_removes_findings_from_text_output(tmp_path, capsys):
    path = write_manifest(tmp_path, MANIFEST)
    code = main([path, "--ignore", "image-tag"])
    out = capsys.readouterr().out
    assert code == 1
    assert "image-tag" not in out
    assert "replicas" in out


def test_cli_ignore_comma_separated_and_repeatable(tmp_path, capsys):
    path = write_manifest(tmp_path, MANIFEST)
    code = main(
        [
            path,
            "--ignore",
            "image-tag,replicas",
            "--ignore",
            "rolling-update, pod-disruption-budget",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip() == f"ok   Deployment/web ({path})"


def test_cli_ignore_removes_findings_from_json(tmp_path, capsys):
    path = write_manifest(tmp_path, MANIFEST)
    code = main([path, "--output", "json", "--ignore", "image-tag"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    findings = out["results"][0]["findings"]
    assert "image-tag" not in check_names(findings)
    assert out["summary"]["errors"] == 0
    assert out["summary"]["warnings"] == len(findings)


def test_cli_unknown_check_name_exits_with_usage_error(tmp_path, capsys):
    path = write_manifest(tmp_path, MANIFEST)
    with pytest.raises(SystemExit) as excinfo:
        main([path, "--ignore", "nope"])
    assert excinfo.value.code == 2
    assert "unknown check(s): nope" in capsys.readouterr().err
