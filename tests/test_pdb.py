"""Tests for the PodDisruptionBudget coverage check."""

import json

from k8s_ready_check.checks import check_pod_disruption_budget, run_all
from k8s_ready_check.cli import main


def make_workload(kind="Deployment", labels=None, namespace=None):
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
    metadata = {"name": "web"}
    if namespace is not None:
        metadata["namespace"] = namespace
    doc = {
        "kind": kind,
        "metadata": metadata,
        "spec": {
            "replicas": 3,
            "strategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxUnavailable": 1, "maxSurge": 1},
            },
            "template": {
                "metadata": {"labels": labels if labels is not None else {"app": "web"}},
                "spec": {
                    "terminationGracePeriodSeconds": 30,
                    "containers": [container],
                },
            },
        },
    }
    return doc


def make_pdb(labels=None, namespace=None):
    metadata = {"name": "web-pdb"}
    if namespace is not None:
        metadata["namespace"] = namespace
    return {
        "kind": "PodDisruptionBudget",
        "metadata": metadata,
        "spec": {
            "minAvailable": 1,
            "selector": {
                "matchLabels": labels if labels is not None else {"app": "web"}
            },
        },
    }


def pdb_findings(findings):
    return [f for f in findings if f["check"] == "pod-disruption-budget"]


def test_missing_pdb_warns():
    findings = run_all(make_workload(), pdbs=[])
    assert len(pdb_findings(findings)) == 1
    assert pdb_findings(findings)[0]["level"] == "warn"


def test_matching_pdb_passes():
    findings = run_all(make_workload(), pdbs=[make_pdb()])
    assert pdb_findings(findings) == []


def test_pdb_selector_subset_of_pod_labels_passes():
    doc = make_workload(labels={"app": "web", "tier": "frontend"})
    findings = run_all(doc, pdbs=[make_pdb(labels={"app": "web"})])
    assert pdb_findings(findings) == []


def test_non_matching_pdb_warns():
    findings = run_all(make_workload(), pdbs=[make_pdb(labels={"app": "api"})])
    assert len(pdb_findings(findings)) == 1


def test_pdb_in_other_namespace_does_not_cover():
    doc = make_workload(namespace="prod")
    findings = run_all(doc, pdbs=[make_pdb(namespace="staging")])
    assert len(pdb_findings(findings)) == 1
    doc_prod = make_workload(namespace="prod")
    findings = run_all(doc_prod, pdbs=[make_pdb(namespace="prod")])
    assert pdb_findings(findings) == []


def test_statefulset_is_checked():
    doc = make_workload(kind="StatefulSet")
    assert len(pdb_findings(run_all(doc, pdbs=[]))) == 1
    assert pdb_findings(run_all(doc, pdbs=[make_pdb()])) == []


def test_non_workload_kinds_skip_pdb_check():
    doc = {"kind": "Service", "metadata": {"name": "web"}, "spec": {}}
    assert pdb_findings(run_all(doc, pdbs=[])) == []
    assert pdb_findings(run_all(make_pdb(), pdbs=[])) == []


def test_no_pdb_info_skips_check():
    # run_all without pdbs keeps single-document callers clean: a
    # budget elsewhere cannot be ruled out from one document alone.
    assert run_all(make_workload()) == []


def test_match_expressions_only_pdb_does_not_cover():
    pdb = make_pdb()
    pdb["spec"]["selector"] = {
        "matchExpressions": [
            {"key": "app", "operator": "In", "values": ["web"]}
        ]
    }
    assert len(pdb_findings(run_all(make_workload(), pdbs=[pdb]))) == 1


def test_check_function_accepts_none():
    assert check_pod_disruption_budget(make_workload(), None) == []


DEPLOYMENT_YAML = """\
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
"""

PDB_YAML = """\
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: web-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels: {app: web}
"""


def write_manifest(tmp_path, content, name):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_cli_pdb_in_same_file_passes(tmp_path, capsys):
    path = write_manifest(
        tmp_path, DEPLOYMENT_YAML + "---\n" + PDB_YAML, "manifest.yaml"
    )
    code = main([path, "--output", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["summary"]["findings"] == 0
    assert out["summary"]["resources"] == 2


def test_cli_deployment_alone_warns(tmp_path, capsys):
    path = write_manifest(tmp_path, DEPLOYMENT_YAML, "deployment.yaml")
    code = main([path, "--output", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    findings = out["results"][0]["findings"]
    assert any(f["check"] == "pod-disruption-budget" for f in findings)


def test_cli_pdb_in_separate_file_passes(tmp_path, capsys):
    dep = write_manifest(tmp_path, DEPLOYMENT_YAML, "deployment.yaml")
    pdb = write_manifest(tmp_path, PDB_YAML, "pdb.yaml")
    code = main([dep, pdb, "--output", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["summary"]["findings"] == 0
    assert out["summary"]["files"] == 2
