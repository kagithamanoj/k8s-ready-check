"""Readiness checks for Kubernetes workload manifests.

Each check takes a parsed manifest dict and returns a list of findings.
Findings are dicts with level ("error", "warn", "ok"), check name, and a
message. Pure functions over dicts, so they are easy to test and reuse.
"""

from __future__ import annotations


def _containers(doc: dict) -> list[dict]:
    try:
        return doc["spec"]["template"]["spec"]["containers"]
    except (KeyError, TypeError):
        return []


def check_probes(doc: dict) -> list[dict]:
    findings = []
    for container in _containers(doc):
        name = container.get("name", "?")
        if "readinessProbe" not in container:
            findings.append(
                {
                    "level": "error",
                    "check": "probes",
                    "message": f"container '{name}' has no readinessProbe",
                }
            )
        if "livenessProbe" not in container:
            findings.append(
                {
                    "level": "warn",
                    "check": "probes",
                    "message": f"container '{name}' has no livenessProbe",
                }
            )
    return findings


def check_resources(doc: dict) -> list[dict]:
    findings = []
    for container in _containers(doc):
        name = container.get("name", "?")
        resources = container.get("resources", {})
        if not resources.get("requests"):
            findings.append(
                {
                    "level": "error",
                    "check": "resources",
                    "message": f"container '{name}' has no resource requests",
                }
            )
        if not resources.get("limits"):
            findings.append(
                {
                    "level": "warn",
                    "check": "resources",
                    "message": f"container '{name}' has no resource limits",
                }
            )
    return findings


def check_image_tags(doc: dict) -> list[dict]:
    findings = []
    for container in _containers(doc):
        name = container.get("name", "?")
        image = container.get("image", "")
        tag = image.rsplit(":", 1)[-1] if ":" in image else ""
        if not tag or tag == "latest":
            findings.append(
                {
                    "level": "error",
                    "check": "image-tag",
                    "message": (
                        f"container '{name}' uses floating image tag "
                        f"'{image or '<none>'}'"
                    ),
                }
            )
    return findings


def check_security_context(doc: dict) -> list[dict]:
    findings = []
    pod_sc = doc.get("spec", {}).get("template", {}).get("spec", {}).get(
        "securityContext", {}
    )
    for container in _containers(doc):
        name = container.get("name", "?")
        sc = container.get("securityContext", {})
        run_as_non_root = sc.get("runAsNonRoot", pod_sc.get("runAsNonRoot"))
        if run_as_non_root is not True:
            findings.append(
                {
                    "level": "warn",
                    "check": "security",
                    "message": (
                        f"container '{name}' does not set runAsNonRoot"
                    ),
                }
            )
        if sc.get("allowPrivilegeEscalation", True):
            findings.append(
                {
                    "level": "warn",
                    "check": "security",
                    "message": (
                        f"container '{name}' allows privilege escalation"
                    ),
                }
            )
    return findings


def _pod_spec(doc: dict) -> dict:
    try:
        return doc["spec"]["template"]["spec"]
    except (KeyError, TypeError):
        return {}


def check_termination_grace(doc: dict) -> list[dict]:
    if not _containers(doc):
        return []
    pod = _pod_spec(doc)
    if "terminationGracePeriodSeconds" not in pod:
        return [
            {
                "level": "warn",
                "check": "termination-grace",
                "message": (
                    "workload does not set "
                    "terminationGracePeriodSeconds; "
                    "Kubernetes defaults to 30 seconds, so set it "
                    "explicitly to match how long shutdown needs"
                ),
            }
        ]
    value = pod["terminationGracePeriodSeconds"]
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        return [
            {
                "level": "warn",
                "check": "termination-grace",
                "message": (
                    f"workload has invalid "
                    f"terminationGracePeriodSeconds '{value}'; "
                    "use a non-negative number of seconds"
                ),
            }
        ]
    return []


def check_rolling_update(doc: dict) -> list[dict]:
    if doc.get("kind") != "Deployment":
        return []
    strategy = doc.get("spec", {}).get("strategy", {}) or {}
    if strategy.get("type", "RollingUpdate") != "RollingUpdate":
        return []
    rolling = strategy.get("rollingUpdate", {}) or {}
    if "maxUnavailable" not in rolling:
        return [
            {
                "level": "warn",
                "check": "rolling-update",
                "message": (
                    "Deployment does not set "
                    "strategy.rollingUpdate.maxUnavailable; "
                    "Kubernetes defaults to 25%, so set it explicitly "
                    "for a predictable rollout"
                ),
            }
        ]
    value = rolling["maxUnavailable"]
    valid = False
    if isinstance(value, int) and not isinstance(value, bool):
        valid = value >= 0
    elif isinstance(value, str) and value.endswith("%"):
        digits = value[:-1]
        valid = digits.isdigit() and 0 <= int(digits) <= 100
    if not valid:
        return [
            {
                "level": "warn",
                "check": "rolling-update",
                "message": (
                    f"Deployment has invalid "
                    f"strategy.rollingUpdate.maxUnavailable "
                    f"'{value}'; use a non-negative count or a "
                    "percentage up to 100%"
                ),
            }
        ]
    return []


def check_replicas(doc: dict) -> list[dict]:
    if doc.get("kind") != "Deployment":
        return []
    replicas = doc.get("spec", {}).get("replicas", 1)
    if replicas < 2:
        return [
            {
                "level": "warn",
                "check": "replicas",
                "message": (
                    f"Deployment has {replicas} replica(s); "
                    "2+ is recommended for availability"
                ),
            }
        ]
    return []


ALL_CHECKS = [
    check_probes,
    check_resources,
    check_image_tags,
    check_security_context,
    check_rolling_update,
    check_termination_grace,
    check_replicas,
]


def run_all(doc: dict) -> list[dict]:
    findings: list[dict] = []
    for check in ALL_CHECKS:
        findings.extend(check(doc))
    return findings
