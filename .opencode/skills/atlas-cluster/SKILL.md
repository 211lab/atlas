---
name: atlas-cluster
description: Use to inspect or operate the live Atlas k3s cluster — topology, nodes, namespaces, workloads, Argo CD application status, ingress/DNS/TLS, storage, credentials and recovery. Triggers on "recon the atlas cluster", "atlas cluster status", "what is running on atlas", "atlas topology", "check atlas", "is atlas healthy", "atlas operations", "kubeconfig atlas".
---

# Atlas cluster — live recon and operations

Point-in-time snapshot of the Atlas k3s cluster plus the commands to re-verify
it. Re-run the cookbook below for the current state; treat this file as the
narrative, not a live cache. Companion docs: `docs/c4-architecture.md`,
`docs/gitops-platform.md`, `docs/kubernetes-control-plane.md`. Deployment skill:
`.opencode/skills/atlas-deploy-app/SKILL.md`.

## Access

```sh
export KUBECONFIG=~/.kube/atlas-admin.yaml   # cluster-admin, embedded client certs
kubectl cluster-info                          # API: https://10.0.0.108:6443 (kube-vip)
kubectl get nodes
```

`*.atlas.lan` is served by Traefik on every node IP. If the workstation does not
resolve it, use `--resolve <host>:443:10.0.0.110` (or add a Pi-hole/hosts entry).
`kubectl`, `helm` and `kubeseal` may need installing (see `AGENTS.md`).

## Verified snapshot — 2026-10-04

### Cluster

| Item | Value |
| --- | --- |
| Distribution | k3s `v1.36.3+k3s1` (containerd 2.3.2-k3s2) |
| API endpoint | `https://10.0.0.108:6443` (kube-vip VIP, lease id `plndr-cp-lock`) |
| Nodes | 3 control-plane/etcd + 1 worker, all `Ready`, 50d |
| Control planes | `atlas-k3s-cp1/2/3` = 10.0.0.110/111/112 (2 vCPU, ~3.8 GiB, schedulable, no taints) |
| Worker | `atlas-k3s-worker1` = 10.0.0.113 (2 vCPU, ~5.7 GiB) |
| Ingress/LB | Traefik `3.7.8` (chart 40.1.4), LoadBalancer ClusterIP 10.43.186.184 via k3s ServiceLB on all nodes |
| DNS (in-cluster) | CoreDNS `1.14.6`; `coredns-custom` maps `*.atlas.lan` → Traefik ClusterIP 10.43.186.184 |
| Metrics | metrics-server `v0.9.0` |

Memory is the tight resource: node usage ~45–64%, and cp2/cp3 memory *limits*
are overcommitted (159% / 128%). Set conservative `requests`/`limits`.

### Namespaces and workloads

`argocd`, `cert-manager`, `demo`, `gitea`, `monitoring`, `redop`,
`sealed-secrets`, `kube-system` (plus empty orphan `external-dns`).

| Namespace | What runs |
| --- | --- |
| `argocd` | Argo CD `v3.5.3` (server, repo-server, application-controller, applicationset-controller, redis) |
| `cert-manager` | cert-manager `v1.21.2`; `atlas-ca` ClusterIssuer |
| `gitea` | Gitea `1.27.0` (chart 12.7.0) + Bitnami PostgreSQL 17 StatefulSet + act_runner StatefulSet (`gitea-actions` chart 0.1.2) |
| `sealed-secrets` | sealed-secrets controller `0.40.0` |
| `monitoring` | kube-prometheus-stack `88.3.0` (operator v0.93.0, Grafana 13.1.3, Prometheus StatefulSet, node-exporter, kube-state-metrics) |
| `demo` | `demo-app` (registry.atlas.lan/atlas-admin/demo-app) |
| `redop` | `redop-api`/`redop-ui`/`redop-postgres`, in-repo chart `apps/redop/chart` |
| `kube-system` | traefik, coredns, metrics-server, local-path-provisioner, csi-driver-nfs `4.13.4`, kube-vip DS, `svclb-*` |

Third-party platform components are upstream charts pinned in
`gitops/apps/*.yaml` with values in `helm/values/*.yaml`. In-house apps use
`apps/<app>/chart`.

### Argo CD (app-of-apps)

`root` (path `gitops/apps`) reconciled from
`http://gitea-http.gitea.svc.cluster.local:3000/atlas-admin/atlas.git` @
`7f21a650`. Children: `argocd`, `atlas-config`, `cert-manager`, `demo-app`,
`gitea`, `gitea-actions`, `redop`, `sealed-secrets`. All `Synced/Healthy`
except **`gitea-actions` = `OutOfSync`** (Helm field noise; runner healthy).

- `atlas-config` applies `gitops/manifests/*` into namespace `cert-manager`
  (cluster-scoped objects: `atlas-ca` ClusterIssuer/Certificate, `truenas-nfs`
  StorageClass, `coredns-custom`, the `helm-bitnamicharts` Argo repo secret).
- `AppProject` `platform` is the only project used by apps (plus `default`).

### Ingress, DNS and TLS

| Host | Backend | Cert |
| --- | --- | --- |
| `git.atlas.lan`, `registry.atlas.lan` | gitea | `gitea-tls` |
| `argocd.atlas.lan` | argocd-server | `argocd-server-tls` |
| `demo.atlas.lan` | demo-app | `demo-app-tls` |
| `redop.atlas.lan` | redop-ui | `redop-tls` |

All ingress class `traefik`; TLS issued by the `atlas-ca` ClusterIssuer
(cert-manager) from the `atlas-ca-tls` Secret. Gitea SSH is a LoadBalancer
(`gitea-ssh-lb`) on port **2222** (`git@git.atlas.lan:2222`). Grafana is a
LoadBalancer on port 3000. `atlas-ca` public cert is also published as
ConfigMaps in `argocd` and `gitea` for in-cluster trust.

### Storage

| Name | Provisioner | Notes |
| --- | --- | --- |
| `local-path` (default) | rancher.io/local-path | node-local, ephemeral/non-platform |
| `truenas-nfs` | nfs.csi.k8s.io | TrueNAS 10.0.10.26, export `/mnt/data/atlas-k8s`, RWX-capable, expansion allowed |

Bound PVCs: `gitea-shared-storage` (10Gi), `data-gitea-postgresql-0` (8Gi),
`data-runner-gitea-actions-runner-0` (1Gi), `redop-data` (10Gi),
`redop-postgres-data` (10Gi). Prometheus is `emptyDir` (7d retention, no PVC).

## Credentials and how to read them

```sh
# Argo CD admin (user admin)
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d

# Gitea admin (keys: username, password, email)
kubectl -n gitea get secret gitea-admin -o jsonpath='{.data.username}{"\n"}{.data.password}' | base64 -d

# Gitea API token used by Argo CD (key: password)
kubectl -n argocd get secret repo-gitea-atlas -o jsonpath='{.data.password}' | base64 -d

# Or mint a new Gitea token (scopes all)
kubectl -n gitea exec deploy/gitea -- gitea admin user generate-access-token -u atlas-admin -n ci-$(date +%s) --scopes all --raw

# atlas-ca public cert
kubectl -n cert-manager get secret atlas-ca-tls -o jsonpath='{.data.tls\.crt}' | base64 -d
```

Seal secrets (kubeseal reaches the controller through the service):

```sh
kubeseal --controller-name sealed-secrets-controller --controller-namespace sealed-secrets \
  --format yaml < plain.yaml > gitops/sealed/<name>.yaml
```

## Recon cookbook

```sh
export KUBECONFIG=~/.kube/atlas-admin.yaml

kubectl get nodes -o wide
kubectl get ns
kubectl get pods -A -o wide
kubectl get deploy,sts,ds -A
kubectl get svc,ingress -A
kubectl get pvc -A; kubectl get sc
kubectl get crd | wc -l
kubectl -n argocd get applications \
  -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status
kubectl top nodes; kubectl top pods -A
kubectl get events -A --field-selector type=Warning --sort-by=.lastTimestamp | tail -20
helm list -A
```

## Known issues and drift

- `gitea-actions` Application `OutOfSync` (Helm-generated field noise) — healthy.
- `external-dns` namespace is empty; no external-dns workloads exist.
- `redop-api` liveness probe intermittently times out.
- Prometheus storage is ephemeral (`emptyDir`, 7d) — no persistence.
- `sealed-secrets` chart appVersion (0.31.0) != running image (0.40.0).
- Only one worker node; control planes are schedulable and carry most pods.
- Control-plane memory limits are overcommitted — prefer requests-based sizing.

## Guardrails

- Git is the source of truth; reconcile changes through Argo CD, not ad-hoc
  `kubectl apply`/`helm install` of platform resources.
- Never commit plaintext secrets; only SealedSecrets.
- Never restart two control planes simultaneously (etcd quorum).
- Don't casually delete/recreate PVCs (storage classes are immutable).
