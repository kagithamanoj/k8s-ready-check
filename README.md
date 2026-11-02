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
k8s-ready-check --ignore replicas,pod-disruption-budget deployment.yaml
```

Exit code is 0 when clean, 1 on warnings, 2 on errors (warnings also fail
with `--strict`).

## Skipping checks

`--ignore` skips checks by name, for findings a team has deliberately
accepted. It is repeatable and accepts comma-separated names:

```bash
k8s-ready-check --ignore replicas --ignore probes,resources deployment.yaml
```

Valid names are the check names from the table below: `probes`,
`resources`, `image-tag`, `security`, `service-account`, `replicas`,
`rolling-update`, `termination-grace`, and `pod-disruption-budget`.
An unknown name is a usage error. Ignored checks produce no findings,
in text or JSON output, and do not affect the exit code.

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

## Check examples

Each example shows only the fields that check looks at. A Bad
snippet triggers that check; the Good snippet clears it. A complete
manifest still needs the other checks to pass as well.

### probes

Bad: a container with no probes.

```yaml
containers:
  - name: app
    image: registry.example.com/app:1.2.3
```

Good: both probes set.

```yaml
containers:
  - name: app
    image: registry.example.com/app:1.2.3
    readinessProbe:
      httpGet:
        path: /
        port: 8080
    livenessProbe:
      httpGet:
        path: /
        port: 8080
```

### resources

Bad: no requests or limits.

```yaml
containers:
  - name: app
    image: registry.example.com/app:1.2.3
```

Good: requests and limits both set.

```yaml
containers:
  - name: app
    image: registry.example.com/app:1.2.3
    resources:
      requests:
        cpu: 100m
        memory: 128Mi
      limits:
        cpu: 500m
        memory: 512Mi
```

### image-tag

Bad: a floating tag.

```yaml
containers:
  - name: app
    image: app:latest
```

Good: a pinned tag.

```yaml
containers:
  - name: app
    image: registry.example.com/app:1.2.3
```

### security

Bad: no security context, so the container can run as root and
escalate privileges.

```yaml
containers:
  - name: app
    image: registry.example.com/app:1.2.3
```

Good: non-root with privilege escalation off.

```yaml
containers:
  - name: app
    image: registry.example.com/app:1.2.3
    securityContext:
      runAsNonRoot: true
      allowPrivilegeEscalation: false
```

### service-account

Bad: no account named, so the pod runs as `default`.

```yaml
spec:
  template:
    spec:
      containers:
        - name: app
```

Good: a dedicated account.

```yaml
spec:
  template:
    spec:
      serviceAccountName: web
      containers:
        - name: app
```

### replicas

Bad: a single replica Deployment.

```yaml
spec:
  replicas: 1
```

Good: three replicas.

```yaml
spec:
  replicas: 3
```

### rolling-update

Bad: a RollingUpdate strategy with no `maxUnavailable` set.

```yaml
spec:
  strategy:
    type: RollingUpdate
```

Good: `maxUnavailable` set explicitly.

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
```

### termination-grace

Bad: no `terminationGracePeriodSeconds` on the pod spec.

```yaml
spec:
  template:
    spec:
      containers:
        - name: app
```

Good: an explicit shutdown window.

```yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
```

### pod-disruption-budget

Bad: a Deployment with no budget covering it.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
        - name: app
```

Good: the same Deployment plus a budget whose selector matches
its pod template labels, in the same namespace.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
        - name: app
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: web
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: web
```

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
