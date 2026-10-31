"""Tests for the ServiceAccount check."""

from k8s_ready_check.checks import check_service_account, run_all


def make_workload(kind="Deployment", service_account=None):
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
    pod_spec = {
        "terminationGracePeriodSeconds": 30,
        "containers": [container],
    }
    if service_account is not None:
        pod_spec["serviceAccountName"] = service_account
    return {
        "kind": kind,
        "metadata": {"name": "web"},
        "spec": {
            "replicas": 3,
            "strategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxUnavailable": 1, "maxSurge": 1},
            },
            "template": {"spec": pod_spec},
        },
    }


def sa_findings(findings):
    return [f for f in findings if f["check"] == "service-account"]


def test_missing_service_account_warns():
    findings = run_all(make_workload(), pdbs=[])
    assert len(sa_findings(findings)) == 1
    assert sa_findings(findings)[0]["level"] == "warn"


def test_explicit_default_service_account_warns():
    findings = run_all(make_workload(service_account="default"), pdbs=[])
    assert len(sa_findings(findings)) == 1
    assert "default" in sa_findings(findings)[0]["message"]


def test_dedicated_service_account_passes():
    findings = run_all(make_workload(service_account="web"), pdbs=[])
    assert sa_findings(findings) == []


def test_legacy_service_account_field_passes():
    doc = make_workload()
    doc["spec"]["template"]["spec"]["serviceAccount"] = "web"
    assert sa_findings(run_all(doc, pdbs=[])) == []


def test_non_string_service_account_warns():
    doc = make_workload()
    doc["spec"]["template"]["spec"]["serviceAccountName"] = 123
    assert len(sa_findings(run_all(doc, pdbs=[]))) == 1


def test_statefulset_is_checked():
    doc = make_workload(kind="StatefulSet")
    assert len(sa_findings(run_all(doc, pdbs=[]))) == 1
    doc = make_workload(kind="StatefulSet", service_account="web")
    assert sa_findings(run_all(doc, pdbs=[])) == []


def test_docs_without_containers_skip_check():
    doc = {"kind": "Service", "metadata": {"name": "web"}, "spec": {}}
    assert sa_findings(run_all(doc, pdbs=[])) == []
    assert check_service_account(doc) == []
