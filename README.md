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

## Development

```bash
pip install pytest pyyaml
pytest
```
