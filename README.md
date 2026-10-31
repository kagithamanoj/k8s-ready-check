# k8s-ready-check

A small CLI that checks Kubernetes workload manifests for
production-readiness basics before you roll them out: probes, resource
requests/limits, pinned image tags, security context, and replica counts.

## Install

```bash
pip install -e .
```

## Use

```bash
k8s-ready-check deployment.yaml
k8s-ready-check --strict manifests/
k8s-ready-check --output json deployment.yaml
```

Exit code is 0 when clean, 1 on warnings, 2 on errors (warnings also fail
with `--strict`).

## Machine-readable output

`--output json` prints a single JSON document instead of text lines, so
CI jobs and other tools can parse the results. Each entry under
`results` names the file, kind, and resource name, with its findings
(level, check, and message) in a list that is empty for a clean
resource. `summary` counts files, resources, findings, errors, and
warnings. Exit codes are the same as in text mode.

```json
{
  "results": [
    {
      "file": "deployment.yaml",
      "kind": "Deployment",
      "name": "web",
      "findings": [
        {
          "level": "error",
          "check": "image-tag",
          "message": "container 'app' uses floating image tag 'app:latest'"
        }
      ]
    }
  ],
  "summary": {
    "files": 1,
    "resources": 1,
    "findings": 1,
    "errors": 1,
    "warnings": 0
  }
}
```

## Checks

| Check | Error when | Warns when |
|---|---|---|
| probes | no readinessProbe | no livenessProbe |
| resources | no requests | no limits |
| image-tag | floating (`latest`/untagged) image | |
| security | | not runAsNonRoot, privilege escalation allowed |
| service-account | | workload without a dedicated serviceAccountName (missing or `default`) |
| replicas | | Deployment with fewer than 2 replicas |
| rolling-update | | Deployment without `strategy.rollingUpdate.maxUnavailable` set (or with an invalid value); `Recreate` strategy is skipped |
| termination-grace | | workload without `terminationGracePeriodSeconds` set (or with an invalid value) |
| pod-disruption-budget | | Deployment or StatefulSet with no PodDisruptionBudget in the same namespace whose selector matches its pod template labels |

## PodDisruptionBudget coverage

A budget covers a workload when it is in the same namespace and
every label in its `spec.selector.matchLabels` also appears on the
workload's pod template labels. The CLI loads all input files before
checking, so a budget in a separate file (or a separate document in
the same file) counts. Matching is by `matchLabels` only; budgets
that select pods with `matchExpressions` are not matched. Checking a
single document through the library without passing the budget list
skips this check, since a budget elsewhere cannot be ruled out from
one document alone.

## ServiceAccount

A pod without `serviceAccountName` runs as the `default`
ServiceAccount for its namespace, which is shared by every workload
that does not name one. Give each workload a dedicated account, so
RBAC can grant only what that workload needs. The older
`serviceAccount` field counts as well.

## Tuning terminationGracePeriodSeconds

Kubernetes defaults this to 30 seconds. Set it explicitly so a pod
is not killed mid-shutdown: raise it when the app needs time to drain
connections or finish in-flight work, and keep it tight when the app
can stop quickly, so rollouts and node drains do not wait longer than
they have to.

## Development

```bash
pip install pytest pyyaml
pytest
```
