"""Tests pinning the Bad/Good examples in the README check section.

Each example is applied to a clean Deployment, so the Bad variant must
trigger only its own check and the Good variant must clear it. The
README section itself must also name every check.
"""

from pathlib import Path

from k8s_ready_check.checks import CHECK_NAMES, run_all


def clean_deployment():
    return {
        "kind": "Deployment",
        "metadata": {"name": "web"},
        "spec": {
            "replicas": 3,
            "strategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxUnavailable": 1},
            },
            "template": {
                "metadata": {"labels": {"app": "web"}},
                "spec": {
                    "serviceAccountName": "web",
                    "terminationGracePeriodSeconds": 30,
                    "containers": [
                        {
                            "name": "app",
                            "image": "registry.example.com/app:1.2.3",
                            "readinessProbe": {
                                "httpGet": {"path": "/", "port": 8080}
                            },
                            "livenessProbe": {
                                "httpGet": {"path": "/", "port": 8080}
                            },
                            "resources": {
                                "requests": {
                                    "cpu": "100m",
                                    "memory": "128Mi",
                                },
                                "limits": {
                                    "cpu": "500m",
                                    "memory": "512Mi",
                                },
                            },
                            "securityContext": {
                                "runAsNonRoot": True,
                                "allowPrivilegeEscalation": False,
                            },
                        }
                    ],
                },
            },
        },
    }


def container(doc):
    return doc["spec"]["template"]["spec"]["containers"][0]


def has_check(findings, check):
    return any(f["check"] == check for f in findings)


def test_readme_names_every_check():
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text()
    section = readme.split("## Check examples", 1)[1].split(
        "## PodDisruptionBudget coverage", 1
    )[0]
    for check in CHECK_NAMES:
        assert check in section


def test_clean_base_passes_all_checks():
    # No budget list is passed, so the PDB check is skipped, as it
    # is for any single-document library call.
    assert run_all(clean_deployment()) == []


def test_probes_example():
    bad = clean_deployment()
    del container(bad)["readinessProbe"]
    del container(bad)["livenessProbe"]
    assert has_check(run_all(bad), "probes")
    assert not has_check(run_all(clean_deployment()), "probes")


def test_resources_example():
    bad = clean_deployment()
    del container(bad)["resources"]
    assert has_check(run_all(bad), "resources")
    assert not has_check(run_all(clean_deployment()), "resources")


def test_image_tag_example():
    bad = clean_deployment()
    container(bad)["image"] = "app:latest"
    assert has_check(run_all(bad), "image-tag")
    assert not has_check(run_all(clean_deployment()), "image-tag")


def test_security_example():
    bad = clean_deployment()
    del container(bad)["securityContext"]
    assert has_check(run_all(bad), "security")
    assert not has_check(run_all(clean_deployment()), "security")


def test_service_account_example():
    bad = clean_deployment()
    del bad["spec"]["template"]["spec"]["serviceAccountName"]
    assert has_check(run_all(bad), "service-account")
    assert not has_check(run_all(clean_deployment()), "service-account")


def test_replicas_example():
    bad = clean_deployment()
    bad["spec"]["replicas"] = 1
    assert has_check(run_all(bad), "replicas")
    assert not has_check(run_all(clean_deployment()), "replicas")


def test_rolling_update_example():
    bad = clean_deployment()
    bad["spec"]["strategy"] = {"type": "RollingUpdate"}
    assert has_check(run_all(bad), "rolling-update")
    assert not has_check(run_all(clean_deployment()), "rolling-update")


def test_termination_grace_example():
    bad = clean_deployment()
    del bad["spec"]["template"]["spec"]["terminationGracePeriodSeconds"]
    assert has_check(run_all(bad), "termination-grace")
    good = clean_deployment()
    good["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] = 60
    assert not has_check(run_all(good), "termination-grace")


def test_pod_disruption_budget_example():
    doc = clean_deployment()
    assert has_check(run_all(doc, pdbs=[]), "pod-disruption-budget")
    pdb = {
        "kind": "PodDisruptionBudget",
        "metadata": {"name": "web"},
        "spec": {
            "minAvailable": 1,
            "selector": {"matchLabels": {"app": "web"}},
        },
    }
    assert not has_check(run_all(doc, pdbs=[pdb]), "pod-disruption-budget")
