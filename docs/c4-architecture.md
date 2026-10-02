# Atlas infrastructure — C4 architecture

> Scope: a complete, current view of the Atlas home lab using the
> [C4 model](https://c4model.com/) (Context → Container → Component →
> Deployment), with supporting views for compute, storage, networking, TLS, and
> the delivery pipeline. Diagrams are Mermaid and render on GitHub.
>
> Verified 2026-10-02. Companion runbooks:
> [Kubernetes control plane](kubernetes-control-plane.md) and
> [GitOps platform](gitops-platform.md).

## How to read this document

| Level | Question it answers | Diagram |
| --- | --- | --- |
| 1 – System Context | Who uses Atlas and what external systems does it depend on? | [`C4Context`](#level-1--system-context) |
| 2 – Container | What are the deployable/running units and how do they talk? | [`C4Container`](#level-2--container) |
| 3 – Component | What is inside the delivery control plane? | [`C4Component`](#level-3--component-delivery-control-plane) |
| 3 – Component | What is inside the network/ingress/TLS layer? | [`C4Component`](#level-3--component-networking-ingress-dns-and-tls) |
| 3 – Component | What is inside the storage layer? | [`C4Component`](#level-3--component-storage) |
| Deployment | Which physical host / VM runs what? | [`C4Deployment`](#deployment-view) |

Supporting views cover [compute](#compute-view), the
[CI/CD and promotion flow](#delivery-flow), the
[request/DNS/TLS flow](#request-flow), and
[storage provisioning](#storage-provisioning).

## Level 1 — System Context

Atlas is a self-hosted Kubernetes platform. Operators and developers interact
with it; it depends on TrueNAS for persistent storage, Pi-hole for internal DNS,
and mirrors its source of truth to GitHub.

```mermaid
C4Context
    title Level 1 — System Context: Atlas home lab platform

    Person(admin, "Lab Administrator", "Operates Proxmox hosts, k3s, Argo CD and the storage layer")
    Person(dev, "Developer", "Pushes application code and tags to the forge")
    Person(grafanaUser, "Observer", "Views Grafana dashboards")

    System(atlas, "Atlas Platform", "Proxmox VE cluster running a highly-available k3s control plane with a self-hosted Gitea forge, container registry, CI runners and an Argo CD GitOps control plane")

    System_Ext(truenas, "TrueNAS", "ZFS storage appliance exporting NFS datasets for persistent volumes")
    System_Ext(pihole, "Pi-hole", "LAN DNS; resolves *.lan (and *.atlas.lan) for workstations")
    System_Ext(github, "GitHub (211lab/atlas)", "Upstream mirror/source of the platform repository")
    System_Ext(workstation, "Operator workstation (Titan / WSL)", "kubectl, helm, git, kubeseal clients")

    Rel(admin, atlas, "Administers over SSH, kubectl and Argo CD")
    Rel(dev, atlas, "Pushes commits/tags, watches CI and deployments")
    Rel(grafanaUser, atlas, "Views metrics and dashboards")
    Rel(workstation, atlas, "kubectl / helm / git over the LAN")
    Rel(atlas, truenas, "Provisions and mounts NFS volumes", "NFSv4.1")
    Rel(atlas, pihole, "Relies on LAN DNS for human hostnames")
    Rel(atlas, github, "Mirrors the GitOps repo to", "git/HTTPS+SSH")
    Rel(pihole, workstation, "Resolves *.lan", "DNS")
    Rel(admin, truenas, "Configures datasets and exports", "HTTPS API")
```

## Level 2 — Container

The platform is a Proxmox VE cluster whose four core hosts run k3s VMs; k3s runs
the platform containers (Traefik ingress, Gitea + registry, CI runner, Argo CD,
cert-manager, Sealed Secrets, monitoring). TrueNAS provides NFS-backed PVCs.

```mermaid
C4Container
    title Level 2 — Container: Atlas platform

    Person(admin, "Lab Administrator")
    Person(dev, "Developer")

    System_Boundary(pve, "Proxmox VE cluster (10.0.0.0/24)") {
        Container_Boundary(k3s, "k3s cluster v1.36.3+k3s1") {
            Container(vip, "kube-vip", "DaemonSet", "Leads the API VIP 10.0.0.108:6443")
            Container(coredns, "CoreDNS", "k3s add-on", "Cluster DNS + atlas.lan host records")
            Container(traefik, "Traefik", "Ingress/LB v3.7.1", "Terminates HTTP/HTTPS on node IPs :80/:443")
            Container(gitea, "Gitea", "Gitea 1.27.0", "Git forge + built-in OCI registry (git.atlas.lan, registry.atlas.lan)")
            ContainerDb(giteapg, "PostgreSQL", "Bitnami 17", "Gitea database")
            Container(runner, "Gitea Actions runner", "act_runner 2.0.1 + dind", "Builds and pushes images")
            Container(argocd, "Argo CD", "v3.5.3", "GitOps app-of-apps controller")
            Container(certmgr, "cert-manager", "v1.21.2", "Issues certs from atlas-ca")
            Container(sealed, "Sealed Secrets", "controller 0.40.0", "Decrypts committed secrets")
            Container(prom, "kube-prometheus-stack", "88.3.0", "Prometheus + Grafana + exporters")
            Container(demo, "demo-app", "nginx", "Example GitOps-deployed workload")
        }
        ContainerDb(pveNodeExporter, "PVE node-exporter", "systemd service", "Physical-host metrics scraped by Prometheus")
    }

    System_Ext(truenas, "TrueNAS 10.0.10.26", "NFSv4.1 server; dataset data/atlas-k8s")
    System_Ext(github, "GitHub 211lab/atlas", "Upstream mirror")
    System_Ext(pihole, "Pi-hole", "LAN DNS")

    Rel(admin, traefik, "HTTPS to *.atlas.lan")
    Rel(dev, traefik, "Pushes to git.atlas.lan / sees argocd.atlas.lan")
    Rel(traefik, gitea, "Routes git/registry hosts")
    Rel(traefik, argocd, "Routes argocd.atlas.lan")
    Rel(traefik, demo, "Routes demo.atlas.lan")
    Rel(gitea, giteapg, "Reads/writes", "TCP 5432")
    Rel(runner, gitea, "Registers, pulls jobs, pushes packages", "HTTP + internal registry")
    Rel(argocd, gitea, "Reads GitOps repo", "HTTPS internal")
    Rel(gitea, argocd, "Sends push webhook", "HTTP /api/webhook")
    Rel(certmgr, traefik, "Provides TLS secrets")
    Rel(gitea, truenas, "Persists data via PVC", "NFSv4.1")
    Rel(giteapg, truenas, "Persists data via PVC", "NFSv4.1")
    Rel(prom, pveNodeExporter, "Scrapes")
    Rel(argocd, github, "Optional mirror", "git")
    Rel(pihole, admin, "Resolves *.lan", "DNS")
```

## Level 3 — Component: delivery control plane

Inside the GitOps/delivery control plane: Argo CD's components, the forge, the
CI runner, and the security primitives.

```mermaid
C4Component
    title Level 3 — Component: GitOps delivery control plane

    Component(root, "root Application", "Argo CD Application", "App-of-apps; reconciles gitops/apps/ from the forge")
    Component(appset, "ApplicationSet controller", "Argo CD", "Generates Applications from generators (available)")
    Component(controller, "Application controller", "Argo CD", "Compares desired vs live state, syncs with selfHeal/prune")
    Component(repoServer, "Repo server", "Argo CD", "Renders Helm/Kustomize from git")
    Component(apiServer, "API server", "Argo CD", "UI/API; receives Gitea push webhooks at /api/webhook")
    Component(redis, "Redis", "Argo CD", "Cache")
    Component(project, "platform AppProject", "Argo CD", "RBAC + source/destination allowlist")

    Component(gitea, "Gitea", "forge", "Repos: atlas (GitOps), demo-app (app source)")
    Component(registry, "Gitea OCI registry", "registry", "Stores built images")
    Component(runner, "act_runner", "CI", "Runs .gitea/workflows/* jobs (docker via dind)")
    Component(sealed, "sealed-secrets-controller", "security", "Unseals committed SealedSecrets")
    Component(certmgr, "cert-manager", "security", "atlas-ca ClusterIssuer -> ingress TLS")
    Component(apps, "gitops/apps/*", "manifests", "One Application per platform component")
    Component(values, "helm/values/*", "values", "Pinned chart values referenced via multi-source")

    Rel(runner, gitea, "Checkout + job API", "HTTP internal")
    Rel(runner, registry, "docker push", "HTTPS + atlas-ca")
    Rel(gitea, apiServer, "push webhook", "HTTP /api/webhook")
    Rel(root, apps, "reads")
    Rel(apps, repoServer, "renders")
    Rel(repoServer, gitea, "clones", "HTTPS internal")
    Rel(values, repoServer, "Helm values ($values ref)")
    Rel(repoServer, controller, "manifests")
    Rel(controller, redis, "cache")
    Rel(apiServer, controller, "triggers refresh")
    Rel(project, controller, "guardrails")
    Rel(sealed, apps, "provides Secrets")
    Rel(certmgr, apps, "provides TLS Secrets")
```

## Level 3 — Component: networking, ingress, DNS and TLS

How a request from a workstation reaches a workload, and how names resolve and
certs are issued.

```mermaid
C4Component
    title Level 3 — Component: networking, ingress, DNS and TLS

    Component(ws, "Workstation client", "curl/browser/kubectl", "e.g. Titan/WSL 10.0.10.166")
    Component(pihole, "Pi-hole", "LAN DNS", "Authoritative for *.lan / *.atlas.lan")
    Component(vip, "kube-vip", "VIP", "API 10.0.0.108:6443")
    Component(svclb, "klipper svclb", "k3s ServiceLB", "Publishes LoadBalancer IPs on node IPs")
    Component(traefik, "Traefik", "Ingress controller", "Entrypoints web :80 / websecure :443")
    Component(coredns, "CoreDNS", "Cluster DNS", "atlas.lan -> Traefik ClusterIP (coredns-custom)")
    Component(certmgr, "cert-manager", "TLS", "atlas-ca ClusterIssuer")
    Component(ca, "atlas-ca", "CA", "Self-signed root -> per-host certs")
    Component(ing, "Ingress resources", "K8s", "git/registry/argocd/demo .atlas.lan")

    Rel(ws, pihole, "DNS query *.atlas.lan", "UDP/TCP 53")
    Rel(ws, svclb, "HTTPS 443", "TLS")
    Rel(svclb, traefik, "forwards")
    Rel(traefik, ing, "matches host/path")
    Rel(ing, certmgr, "requests cert", "cert-manager.io/cluster-issuer")
    Rel(certmgr, ca, "signs with")
    Rel(ca, traefik, "TLS secret mounted")
    Rel(coredns, traefik, "resolves in-cluster *.atlas.lan -> ClusterIP")
    Rel(ws, vip, "kubectl API", "TLS 6443")
```

## Level 3 — Component: storage

Persistent volumes come from TrueNAS over NFS via the `nfs.csi.k8s.io` driver;
`local-path` remains the cluster default for non-platform workloads.

```mermaid
C4Component
    title Level 3 — Component: storage

    Component(sc, "StorageClass truenas-nfs", "nfs.csi.k8s.io", "NFSv4.1, subDir per PVC, Immediate")
    Component(lp, "StorageClass local-path (default)", "rancher.io/local-path", "Node-local; default for other workloads")
    Component(ctrl, "csi-driver-nfs controller", "csi-driver-nfs 4.13.4", "Provisions subdirectories")
    Component(node, "csi-nfs-node DaemonSet", "csi-driver-nfs 4.13.4", "Mounts NFS on nodes")
    ComponentDb(giteaPVC, "gitea-shared-storage", "PVC 10Gi", "Gitea repositories, LFS, packages")
    ComponentDb(pgPVC, "data-gitea-postgresql-0", "PVC 8Gi", "Gitea database")
    ComponentDb(runnerPVC, "data-runner-...-0", "PVC 1Gi", "Runner state")
    System_Ext(truenas, "TrueNAS", "pool 'data', dataset data/atlas-k8s, export /mnt/data/atlas-k8s")

    Rel(giteaPVC, sc, "requests")
    Rel(pgPVC, sc, "requests")
    Rel(runnerPVC, sc, "requests")
    Rel(sc, ctrl, "provision")
    Rel(ctrl, truenas, "mkdir + export", "NFS")
    Rel(node, truenas, "mount", "NFSv4.1")
```

## Deployment view

Physical and logical placement: Proxmox hosts → k3s VMs → pods, plus TrueNAS.

```mermaid
C4Deployment
    title Deployment — physical and logical placement

    Deployment_Node(pve, "Proxmox VE cluster", "6 bare-metal hosts, 10.0.0.101-106") {
        Deployment_Node(turing, "Turing 10.0.0.101", "PVE host") {
            Deployment_Node(cp1, "atlas-k3s-cp1 / VM 201", "Ubuntu 24.04, 2 vCPU, 3.8 GiB, 10.0.0.110") {
                Container(k3s1, "k3s server + etcd + kube-vip", "control plane")
            }
        }
        Deployment_Node(hopper, "Hopper 10.0.0.102", "PVE host") {
            Deployment_Node(cp2, "atlas-k3s-cp2 / VM 202", "Ubuntu 24.04, 2 vCPU, 3.8 GiB, 10.0.0.111") {
                Container(k3s2, "k3s server + etcd + kube-vip", "control plane")
            }
        }
        Deployment_Node(lovelace, "Lovelace 10.0.0.103", "PVE host") {
            Deployment_Node(cp3, "atlas-k3s-cp3 / VM 203", "Ubuntu 24.04, 2 vCPU, 3.8 GiB, 10.0.0.112") {
                Container(k3s3, "k3s server + etcd + kube-vip", "control plane")
            }
        }
        Deployment_Node(babbage, "Babbage 10.0.0.104", "PVE host") {
            Deployment_Node(wk, "atlas-k3s-worker1 / VM 204", "Ubuntu 24.04, 2 vCPU, 5.7 GiB, 10.0.0.113") {
                Container(pods, "Platform + app pods", "Gitea, Argo CD, runner, monitoring, demo-app")
            }
        }
        Deployment_Node(extra, "Memex 10.0.0.105 / Minsky 10.0.0.106", "Additional PVE/Ubuntu hosts", "Non-k3s lab services")
    }

    Deployment_Node(tn, "TrueNAS (10.0.10.26)", "Storage appliance") {
        Deployment_Node(pool, "ZFS pool 'data'", "datasets: atlas-k8s, movies, pictures, series") {
            ContainerDb(export, "NFS export", "/mnt/data/atlas-k8s")
        }
    }

    Deployment_Node(ws, "Operator workstation", "Titan / WSL 10.0.10.166") {
        Container(cli, "kubectl / helm / git / kubeseal", "admin tooling")
    }

    Rel(cli, k3s1, "kubectl via VIP 10.0.0.108:6443")
    Rel(pods, export, "NFSv4.1 PVCs")
    Rel(k3s1, k3s2, "etcd peer")
    Rel(k3s2, k3s3, "etcd peer")
```

## Compute view

| Layer | Name | Address | Role | Capacity |
| --- | --- | --- | --- | --- |
| PVE host | Turing | 10.0.0.101 | Proxmox; hosts VM 201 | — |
| PVE host | Hopper | 10.0.0.102 | Proxmox; hosts VM 202 | — |
| PVE host | Lovelace | 10.0.0.103 | Proxmox; hosts VM 203 | — |
| PVE host | Babbage | 10.0.0.104 | Proxmox; hosts VM 204 | — |
| PVE host | Memex | 10.0.0.105 | Additional host (standalone) | — |
| PVE host | Minsky | 10.0.0.106 | Additional Ubuntu host | — |
| k3s node | atlas-k3s-cp1 | 10.0.0.110 (VM 201) | control-plane, embedded etcd | 2 vCPU / 3.8 GiB |
| k3s node | atlas-k3s-cp2 | 10.0.0.111 (VM 202) | control-plane, embedded etcd | 2 vCPU / 3.8 GiB |
| k3s node | atlas-k3s-cp3 | 10.0.0.112 (VM 203) | control-plane, embedded etcd | 2 vCPU / 3.8 GiB |
| k3s node | atlas-k3s-worker1 | 10.0.0.113 (VM 204) | worker | 2 vCPU / 5.7 GiB |
| API VIP | kube-vip | 10.0.0.108:6443 | HA Kubernetes API | — |

Totals: **8 vCPU / ~17.7 GiB** across the k3s layer; typical steady-state use
~25–35 % memory. Because only one node is a worker, platform stateful workloads
are scheduled there unless they use NFS (which is node-independent).

## Request flow

```mermaid
flowchart LR
    A[Browser / curl / kubectl] --> B{Pi-hole DNS}
    B -- *.atlas.lan --> C[Node IP :443 / :6443]
    C -- :6443 --> V[kube-vip VIP 10.0.0.108]
    V --> API[k3s API server]
    C -- :443 --> S[svclb -> Traefik]
    S --> T{Traefik routes by Host}
    T -- git.atlas.lan --> G[Gitea]
    T -- registry.atlas.lan --> R[Gitea registry]
    T -- argocd.atlas.lan --> AR[Argo CD server]
    T -- demo.atlas.lan --> D[demo-app]
    G & R & AR & D --> TLS[(atlas-ca TLS secret)]
```

## Delivery flow

```mermaid
flowchart TD
    Dev[Developer] -->|git push / tag v*| G[Gitea: demo-app repo]
    G -->|Actions job| Runner[act_runner + dind]
    Runner -->|docker build/push| Reg[registry.atlas.lan/atlas-admin/demo-app]
    Runner -->|commits tag| Repo[Gitea: atlas GitOps repo]
    Repo -->|push webhook| Argo[Argo CD /api/webhook]
    Argo -->|app-of-apps sync| K8s[Deployments / Helm releases]
    K8s --> Demo[demo-app running new tag]
    Repo -. mirror .-> Hub[GitHub 211lab/atlas]
```

## Storage provisioning

```mermaid
sequenceDiagram
    participant U as Argo CD / app chart
    participant K as Kubernetes
    participant C as csi-driver-nfs controller
    participant N as csi-nfs-node
    participant T as TrueNAS (NFSv4.1)
    U->>K: create PVC (storageClass: truenas-nfs)
    K->>C: provision volume
    C->>T: mkdir <server>/<export>/<namespace>/<pvc>
    C-->>K: PV bound (RWX)
    K->>N: mount on consuming node
    N->>T: NFS mount (nfsvers=4.1)
    N-->>U: volume available at pod mountPath
```

## Trust and security boundaries

- **Layer separation**: Proxmox root ≠ guest `control`/`ubuntu` ≠ Kubernetes
  admin kubeconfig ≠ Argo CD RBAC. A credential for one layer does not grant the
  next.
- **TLS**: a single internal CA (`atlas-ca`) signs all `*.atlas.lan` certs.
  Workstations and k3s nodes trust it explicitly; public trust is not assumed.
- **Secrets**: never committed in plaintext. Sealed Secrets encrypt them at rest
  in git; the controller's private key is the only in-cluster decryption key.
- **Registry/CI**: the runner pushes to the private registry over TLS validated
  by `atlas-ca`; workloads pull with a per-namespace image pull secret.
- **Webhook path**: Gitea must be explicitly allowed to call the in-cluster Argo
  CD service (`GITEA__security__ALLOWED_HOST_LIST`), and the payload is
  HMAC-verified with the shared secret in `argocd-webhook`.

## Inventory quick reference

| Concern | Value |
| --- | --- |
| Kubernetes | k3s v1.36.3+k3s1, 3× control-plane/etcd + 1 worker |
| API endpoint | https://10.0.0.108:6443 (kube-vip) |
| Ingress hosts | `git.atlas.lan`, `registry.atlas.lan`, `argocd.atlas.lan`, `demo.atlas.lan` |
| DNS | Pi-hole (LAN) + CoreDNS `coredns-custom` (in-cluster) |
| TLS CA | `atlas-ca` ClusterIssuer (cert-manager v1.21.2) |
| Forge/registry | Gitea 1.27.0, PostgreSQL 17, built-in OCI registry |
| Git over SSH | `ssh://git@git.atlas.lan:2222/<owner>/<repo>.git` (`gitea-ssh-lb`, ServiceLB) |
| CI | Gitea Actions (act_runner 2.0.1) with dind, `docker:25-git` job image |
| CD | Argo CD v3.5.3 (app-of-apps), Gitea push webhook, 60s git poll fallback |
| Storage | TrueNAS NFS (`truenas-nfs`) for platform data; `local-path` default |
| Observability | kube-prometheus-stack 88.3.0 (Prometheus, Grafana, exporters) |
| Secrets | Sealed Secrets controller 0.40.0 |
| Upstream mirror | github.com/211lab/atlas |

## Gaps and future work

- **Single worker node**: only `atlas-k3s-worker1` schedules general workloads;
  adding a second worker would improve resilience and capacity.
- **Prometheus storage** is ephemeral (no PVC); wire it to `truenas-nfs` for
  retention.
- **`gitea-actions` Application** reports `OutOfSync` (Helm-generated field
  noise); it is healthy and functional.
- **Titan Windows exporter** is not yet installed (physical-host Windows
  metrics).
- **TrueNAS `movies` export** is intentionally left untouched and is unrelated
  to Kubernetes storage.
