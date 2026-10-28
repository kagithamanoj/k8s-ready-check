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
```

Exit code is 0 when clean, 1 on warnings, 2 on errors (warnings also fail
with `--strict`).

## Checks

| Check | Error when | Warns when |
|---|---|---|
| probes | no readinessProbe | no livenessProbe |
| resources | no requests | no limits |
| image-tag | floating (`latest`/untagged) image | |
| security | | not runAsNonRoot, privilege escalation allowed |
| replicas | | Deployment with fewer than 2 replicas |
| rolling-update | | Deployment without `strategy.rollingUpdate.maxUnavailable` set (or with an invalid value); `Recreate` strategy is skipped |
| termination-grace | | workload without `terminationGracePeriodSeconds` set (or with an invalid value) |

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
