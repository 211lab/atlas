# AGENTS.md — working in the Atlas repo

Atlas is a home-lab Kubernetes platform (Proxmox VE hosts → a 4-node HA k3s
cluster running Gitea, Argo CD, monitoring and demo/redop apps). **This repo is
the GitOps source of truth**: applications and platform components are declared
here and reconciled by Argo CD. Change git, let controllers converge the cluster
— do not `helm install` / `kubectl apply` platform changes by hand.

Read these before making changes:

- `docs/gitops-platform.md` — forge, registry, CI, Argo CD, secrets, storage
- `docs/c4-architecture.md` — full context/container/component/deployment views
- `docs/kubernetes-control-plane.md` — HA topology, access, recovery
- `.opencode/skills/atlas-deploy-app/SKILL.md` — onboard a new app end to end
- `.opencode/skills/atlas-cluster/SKILL.md` — live cluster recon, topology and ops

## Access

```sh
export KUBECONFIG=~/.kube/atlas-admin.yaml   # cluster-admin (embedded client certs)
export PATH="$HOME/.local/bin:$PATH"

kubectl cluster-info          # API: https://10.0.0.108:6443 (kube-vip VIP)
kubectl get nodes
kubectl -n argocd get applications
```

Tooling is not always preinstalled on a fresh workstation. Install to
`~/.local/bin` (kubectl/helm/kubeseal):

```sh
mkdir -p ~/.local/bin
curl -sSL "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" -o ~/.local/bin/kubectl && chmod +x ~/.local/bin/kubectl
curl -sSL https://get.helm.sh/helm-v3.16.4-linux-amd64.tar.gz | tar xz -C /tmp && mv /tmp/linux-amd64/helm ~/.local/bin/
curl -sSL "https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.40.0/kubeseal-0.40.0-linux-amd64.tar.gz" | tar xz -C ~/.local/bin kubeseal
```

Forge / UI endpoints (Gitea `git.atlas.lan`, Argo CD `argocd.atlas.lan`) are
served by Traefik on every node IP. Workstations may not resolve `*.atlas.lan`;
add a Pi-hole/hosts entry or fall back to `--resolve`:

```sh
curl -ksS --resolve git.atlas.lan:443:10.0.0.110 https://git.atlas.lan/
git remote add atlas ssh://git@git.atlas.lan:2222/atlas-admin/atlas.git
```

## Repo layout

```
apps/<app>/chart/            in-repo Helm chart for an application (redop, immich)
gitops/apps/<name>.yaml      one Argo CD Application per component (app-of-apps)
gitops/bootstrap/root-app.yaml  app-of-apps root (bootstrap once)
gitops/manifests/            cluster-scoped raw manifests, applied by atlas-config
gitops/sealed/               SealedSecrets (safe to commit)
helm/values/<name>.yaml      pinned values for platform components
examples/demo-app/           canonical worked example (CI + chart + promotion)
docs/                        runbooks and architecture
.opencode/skills/            opencode skills for agents
```

## Conventions

- **App-of-apps**: `root` reconciles everything under `gitops/apps/`. Add a new
  component by adding a `gitops/apps/<name>.yaml` `Application`; never create
  resources imperatively.
- **Two app styles** — follow the existing precedent:
  - *Third-party stack* (gitea, argocd, cert-manager, sealed-secrets): upstream
    chart in `gitops/apps/<name>.yaml` + pinned values in `helm/values/<name>.yaml`
    referenced with the `$values` multi-source ref.
  - *In-house app* (redop, immich): an in-repo chart under `apps/<app>/chart`
    with its own `values.yaml`, referenced by `gitops/apps/<app>.yaml`.
- **Pin versions**: chart `targetRevision` and image tags are pinned in git.
- **Never hand-edit image tags** that CI promotes (`ci: promote <app> <tag>`).
- **Secrets**: only SealedSecrets in git. Seal with `kubeseal` against
  `sealed-secrets-controller` in the `sealed-secrets` namespace.
- **Namespaced global manifests** belong with their app; `gitops/manifests/` is
  applied by `atlas-config` into namespace `cert-manager`, so it should only hold
  cluster-scoped objects (ClusterIssuer, StorageClass, CoreDNS ConfigMap, …).
- Prefix Argo CD Applications with `argocd.argoproj.io/sync-wave` when one must
  come first (e.g. a CRD-providing operator before its CRs).

## Validate before you commit

```sh
# Render any in-repo chart
helm template <app> apps/<app>/chart -n <ns> -f apps/<app>/chart/values.yaml

# Render a platform component with its pinned values (repo root)
helm template <name> <repo>/<chart> --version <ver> -n <ns> -f helm/values/<name>.yaml

# After pushing: confirm Argo reconciled
kubectl -n argocd get application <name> \
  -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status
kubectl -n <ns> get deploy,po,ingress,certificate
```

## Guardrails

- Never commit plaintext secrets, tokens, or kubeconfigs.
- Never restart two control-plane nodes at once (etcd quorum).
- Mind memory pressure: control planes run hot (cp2/cp3 limits already >100%
  overcommitted; ~45–64% memory used). Set realistic `requests`/`limits`.
- There is a single worker (`atlas-k3s-worker1`); stateful platform data uses the
  `truenas-nfs` StorageClass (TrueNAS NFS). `local-path` is the cluster default
  for ephemeral/non-platform workloads only.
- PVC storage classes are immutable — a wrong `storageClassName` means recreating
  the PVC.
- `docs/` and these instructions are the source of truth for ops; update them
  when behavior changes.

## Known issues / drift (verified 2026-10-04)

- `gitea-actions` Application is `OutOfSync` (Helm-generated field noise); the
  runner is healthy and functional.
- `external-dns` namespace exists but is empty — an orphaned/abandoned install.
- `redop-api` liveness probe intermittently times out (event noise).
- Prometheus retention is 7d on `emptyDir` (ephemeral); no PVC.
- The `sealed-secrets` chart reports appVersion 0.31.0 but the image is 0.40.0
  (pinned via values).
- `docs/gitops-platform.md` says to re-seal `atlas-ca` ConfigMaps; the live CA
  is the `atlas-ca-tls` Secret, and `atlas-ca` ConfigMaps exist only in
  `argocd` and `gitea` (not `cert-manager`).

## Open work / pending decisions

In flight in this repo — extend rather than duplicate or contradict:

- **`docs/adr-service-naming-reachability`** — ADR 0001 (service naming and
  reachability: `atlas.lan` is the canonical namespace, Pi-hole becomes a
  Tailscale DNS resolver, `*.ts.net` for publicly-trusted TLS). Status:
  *Proposed*; not on `main` yet.
- **`feat/pihole-dns-autoregistration`** — a dedicated Pi-hole Ansible role,
  `docs/pihole-dns.md`, an `external-dns` Application + `helm/values/external-dns.yaml`,
  and `gitops/sealed/pihole-api.yaml` for automatic Ingress DNS registration. The
  empty `external-dns` namespace on the cluster is a remnant of this work.
- **`feat/immich`** — Immich + CloudNativePG deployment (see
  [Applications](docs/applications.md)).
- `apps/redop/chart/values.yaml` cites "ADR 0003", but no `docs/adr/` exists on
  `main` yet — ADR numbering is not established here.
