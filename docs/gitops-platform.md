# Atlas GitOps platform runbook

> See [C4 architecture](c4-architecture.md) for the full system/container/component/deployment views.

> Scope: a self-contained git forge (Gitea) and continuous delivery control
> plane (Argo CD) running on the Atlas k3s cluster, plus a build runner and an
> automated image-promotion loop. All configuration is Helm-driven and stored in
> this repository as the source of truth.

## Current deployed platform

Verified 2026-10-02.

| Component | Chart | Version | Namespace | Access |
| --- | --- | --- | --- | --- |
| cert-manager | `jetstack/cert-manager` | v1.21.2 | cert-manager | internal |
| Sealed Secrets | `bitnamicharts/sealed-secrets` (OCI) | 2.5.19 / controller 0.40.0 | sealed-secrets | internal |
| Gitea (+ bundled PostgreSQL) | `gitea/gitea` | 12.7.0 / Gitea 1.27.0 | gitea | https://git.atlas.lan |
| Container registry | Gitea built-in | — | gitea | https://registry.atlas.lan |
| Gitea Actions runner | `gitea/actions` | 0.1.2 / runner 2.0.1 | gitea | — |
| Argo CD | `argo/argo-cd` | 10.9.6 / v3.5.3 | argocd | https://argocd.atlas.lan |
| Demo app | in-repo chart | 0.1.0 | demo | https://demo.atlas.lan |

Ansible-managed cluster access (SSH, API, Proxmox) is documented separately in
[Kubernetes control plane](kubernetes-control-plane.md).

## Architecture

```
developer push/tag ──▶ Gitea (git + OCI registry)
                          │
                          ▼
              Gitea Actions (act_runner + dind)
                 │  builds image, pushes to
                 ▼
        registry.atlas.lan/atlas-admin/<app>:<tag>
                 │
                 │  (same job) commits the new tag into the GitOps repo
                 ▼
        atlas GitOps repo ──push webhook──▶ Argo CD /api/webhook
                 │                              (instant; 60s git poll fallback)
                 ▼
              Argo CD (app-of-apps) ── reconciles ──▶ k3s workloads
```

There is **no registry poller**: Argo CD core does not watch container
registries, so the build job itself writes the new tag back to git and Gitea
notifies Argo CD. This keeps git as the single source of truth and removes the
need for a separate `argocd-image-updater` deployment.

- **GitOps layout is an app-of-apps**: a root `Application` points at
  `gitops/apps/`, and every file there is an `Application` that Argo CD manages.
- **Helm values live in git**, referenced from each Application using Argo CD
  multi-source (`$values` ref to this repo) so chart versions stay pinned and
  values remain reviewable.
- **Secrets live in git as SealedSecrets** (encrypted) and are decrypted in
  cluster by the controller.

## Repository layout

```
atlas/
  gitops/
    bootstrap/root-app.yaml     app-of-apps root (bootstrap once)
    projects/platform.yaml      Argo CD AppProject
    apps/                       one Application per component
    manifests/                  raw manifests: atlas-ca, coredns, StorageClass
    sealed/                     encrypted SealedSecrets (safe to commit)
  helm/values/                  pinned values.yaml per chart
  examples/demo-app/            demo app: Dockerfile, index.html, chart/, .gitea CI
  docs/gitops-platform.md       this runbook
```

## Access and credentials

| What | How to read it |
| --- | --- |
| Gitea admin | `kubectl -n gitea get secret gitea-admin -o jsonpath='{.data.username}{"\n"}{.data.password}' \| ...` (base64-decode) |
| Gitea API token (argocd/ci) | `kubectl -n gitea exec deploy/gitea -- gitea admin user generate-access-token -u atlas-admin -n <name> --scopes all --raw` |
| Argo CD admin | `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' \| base64 -d` (user `admin`) |
| Cluster CA | `kubectl -n cert-manager get secret atlas-ca-tls -o jsonpath='{.data.tls\.crt}' \| base64 -d` |

Hostnames resolve from the lab network via Pi-hole and inside the cluster via a
CoreDNS `coredns-custom` ConfigMap (`gitops/manifests/coredns-atlas.yaml`)
pointing `*.atlas.lan` at the Traefik ClusterIP.

## How it was built (reproduce from scratch)

1. **cert-manager + internal CA + Sealed Secrets**
   ```sh
   helm upgrade --install cert-manager jetstack/cert-manager -n cert-manager \
     --create-namespace --version v1.21.2 --set crds.enabled=true
   kubectl apply -f gitops/manifests/issuers-atlas-ca.yaml     # atlas-ca ClusterIssuer
   helm upgrade --install sealed-secrets \
     oci://registry-1.docker.io/bitnamicharts/sealed-secrets -n sealed-secrets \
     --create-namespace --version 2.5.19 --set image.tag=0.40.0 \
     --set fullnameOverride=sealed-secrets-controller
   ```
2. **Storage** — apply `gitops/manifests/storageclass-truenas.yaml`. Stateful
   workloads use the `truenas-nfs` StorageClass backed by the TrueNAS dataset
   `data/atlas-k8s` (see Storage below).
3. **Secrets** — create the plaintext secrets and seal them:
   ```sh
   kubeseal --controller-name sealed-secrets-controller \
     --controller-namespace sealed-secrets --format yaml < secret.yaml > sealed.yaml
   kubectl apply -f gitops/sealed/
   ```
4. **Gitea** — `helm upgrade --install gitea gitea/gitea -n gitea -f helm/values/gitea.yaml`.
5. **CI runner** — `helm upgrade --install gitea-actions gitea/actions -n gitea -f helm/values/gitea-actions.yaml`.
6. **Argo CD** — `helm upgrade --install argocd argo/argo-cd -n argocd --create-namespace -f helm/values/argocd.yaml`.
   Argo CD's value file references the sealed `argocd-webhook` secret via the
   `$argocd-webhook:webhook.gogs.secret` indirection. Register the Gitea repo
   credential (SealedSecret `argocd-repo-gitea`), then:
   ```sh
   kubectl apply -f gitops/projects/platform.yaml
   kubectl apply -f gitops/bootstrap/root-app.yaml
   ```
7. **Gitea → Argo CD webhook** — in the platform repo
   (`atlas-admin/atlas`) add a **Gogs**-type webhook to
   `http://argocd-server.argocd.svc.cluster.local/api/webhook` (JSON, push
   events) with the same secret as `argocd-webhook`. Gitea must be allowed to
   call in-cluster hosts (`GITEA__security__ALLOWED_HOST_LIST`, set in
   `helm/values/gitea.yaml`).
8. **Push this repo to Gitea** and tag the demo app; Argo CD takes over from there.

## Using the platform (add a new application)

1. Create a repo in Gitea (e.g. `atlas-admin/myapp`). Add repo Actions secrets
   `REGISTRY_USER` and `REGISTRY_TOKEN` (a Gitea PAT with `write:package` and
   repo write access so CI can promote into the GitOps repo).
2. Add a `.gitea/workflows/build.yaml` modelled on
   `examples/demo-app/.gitea/workflows/build.yaml`: checkout over the internal
   Gitea service, write `~/.docker/config.json`, `docker build`/`push` to
   `registry.atlas.lan/atlas-admin/<app>:<tag>`, then for semver tags commit the
   new tag into this repo's Helm values.
3. Add a Helm chart and a GitOps `Application` under `gitops/apps/` with:
   - `source.repoURL` = this repo, `path` = chart path, `helm.valueFiles`.
   - `destination.namespace` for the app.
4. Commit; the Gitea webhook triggers Argo CD (60s git poll as fallback).

### How image promotion works

The build job that pushes an image already knows its tag, so it performs the
promotion directly:

1. On a `v*` tag push, CI builds/pushes `registry.atlas.lan/<org>/<app>:<tag>`.
2. The same job clones this repo, sets `image.tag` in the app's Helm
   `values.yaml`, commits, and pushes.
3. Gitea delivers a **Gogs-format webhook** to Argo CD's `/api/webhook`, which
   refreshes the matching Application; Argo CD syncs within seconds. Argo CD's
   own 60-second git poll is the fallback.

This is the standard CI-writes-to-git promotion pattern and needs no registry
polling component. Note that Argo CD core does not watch container registries;
its built-in monitoring is limited to Git polling and webhooks (plus OCI
*artifact* webhooks for Applications sourced directly from an OCI chart).

## Sealed Secrets workflow

```sh
# write a normal Secret, seal it, commit only the SealedSecret
kubeseal --controller-name sealed-secrets-controller \
  --controller-namespace sealed-secrets --format yaml < plain.yaml > gitops/sealed/name.yaml
kubectl apply -f gitops/sealed/name.yaml
```

The controller private key lives in the `sealed-secrets` namespace. Back it up
(`kubectl -n sealed-secrets get secret -l sealedsecrets.bitnami.com/sealed-secrets-key`)
or existing manifests cannot be unsealed after a controller rebuild; if lost,
re-seal everything from the plaintext sources.

## Storage

Stateful workloads (Gitea, Postgres, the Actions runner) run on the
`truenas-nfs` StorageClass (csi-driver-nfs, NFSv4.1, `subDir` per PVC):

| Item | Value |
| --- | --- |
| TrueNAS server | 10.0.10.26 |
| Dataset | `data/atlas-k8s` |
| NFS export | `/mnt/data/atlas-k8s`, id 6, `mapall root`, networks `10.0.0.0/24,10.0.10.0/24` |
| StorageClass | `truenas-nfs` (`share: /mnt/data/atlas-k8s`) |

The dataset and export were created via the TrueNAS API with a dedicated
`atlas-k8s` user + API key. To re-provision from scratch:

```
GET  /api/v2.0/pool/dataset              # find the pool (here: data)
POST /api/v2.0/pool/dataset              # {"name":"data/atlas-k8s"}
POST /api/v2.0/sharing/nfs               # path, networks, mapall_user/group root, security ["SYS"]
POST /api/v2.0/service/start             # {"service":"nfs"}
```

**NFS + Postgres:** the bundled PostgreSQL chart needs
`postgresql.volumePermissions.enabled: true` so an init container can chown the
NFS data directory; without it the Bitnami entrypoint exits silently during
initialization. This is set in `helm/values/gitea.yaml`.

PVC storage classes are immutable, so the original `local-path` forge was
rebuilt on NFS (dataset + export created first). `local-path` remains the
cluster default for non-platform workloads.

## Node registry trust

The private registry is served over TLS with the internal `atlas-ca`. Each k3s
node has:

```
# /etc/hosts
10.43.186.184 registry.atlas.lan git.atlas.lan argocd.atlas.lan demo.atlas.lan

# /etc/rancher/k3s/registries.yaml
mirrors:
  registry.atlas.lan:
    endpoint: ["https://registry.atlas.lan"]
configs:
  "registry.atlas.lan":
    tls:
      ca_file: /etc/rancher/k3s/atlas-ca.crt
```

After editing, `systemctl restart k3s` (servers) / `k3s-agent` (worker) one node
at a time, keeping etcd quorum (never restart two control planes at once).

## Day-2 operations

```sh
export KUBECONFIG=~/.kube/atlas-admin.yaml
# status
kubectl -n argocd get applications
# force a refresh after pushing git changes (webhook does this automatically)
kubectl -n argocd annotate application <name> argocd.argoproj.io/refresh=hard --overwrite
# upgrade a component: bump the chart version in gitops/apps/<name>.yaml,
# adjust helm/values/<name>.yaml, commit, let Argo sync (or refresh).
```

## Known issues and deviations

- **Kaniko vs docker:** the plan called for Kaniko, but the pinned `executor:debug`
  image has no `/bin/sleep`, which the Gitea act_runner uses as the job container
  keep-alive, so the job is cancelled. The demo pipeline therefore builds with
  the runner's dind using `docker:25-git`. A Kaniko variant can be reintroduced
  once a compatible runner/image pair is validated.
- **`docker login` vs config.json:** `docker login` fails against Gitea's token
  registry during credential validation; the workflow writes
  `~/.docker/config.json` directly instead.
- **gitea-actions OutOfSync:** Argo CD reports the runner StatefulSet OutOfSync
  due to Helm-generated fields; it is healthy and functional.
- **Gitea pod must be `Recreate`:** Gitea is a single-writer app on a shared PVC;
  the default `RollingUpdate` deadlocks on the leveldb lock. `strategy.type:
  Recreate` is set in `helm/values/gitea.yaml`.
- **Gitea webhook host allowlist:** outbound webhooks to in-cluster services are
  blocked unless `GITEA__security__ALLOWED_HOST_LIST` includes `private` (set via
  `gitea.additionalConfigFromEnvs`).
- **Titan Windows exporter** remains pending from the infrastructure runbook.

## Recovery

- **Argo CD lost:** `kubectl apply -f gitops/bootstrap/root-app.yaml` recreates
  every Application; credentials come from the SealedSecrets.
- **Gitea lost:** restore Postgres and Gitea PVCs (or reinstall via Helm); the
  git content is the source of truth and can be re-pushed to a fresh forge.
- **Registry unreachable:** check `kubectl -n gitea get pods` and the Traefik
  ingress; confirm `registry.atlas.lan` resolves on the nodes.
- **CA lost:** re-apply `gitops/manifests/issuers-atlas-ca.yaml`, re-copy the CA
  to the nodes, reissue certs, and re-seal `atlas-ca` ConfigMaps.

## References

- [Gitea Helm chart](https://gitea.com/gitea/helm-gitea)
- [Gitea Actions](https://docs.gitea.com/usage/actions/overview)
- [Argo CD](https://argo-cd.readthedocs.io/) and [Argo CD webhooks](https://argo-cd.readthedocs.io/en/stable/operator-manual/webhook/)
- [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets)
- [cert-manager](https://cert-manager.io/docs/)
