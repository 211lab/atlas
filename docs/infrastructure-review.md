# Atlas infrastructure review

## Evidence and scope

**Collection:** using the workstation's machine clock (`date -u`). These are
point-in-time observations, not ongoing monitoring. Later verification commands
do not silently refresh these tables.

Evidence keys used throughout this review and its linked architecture pages:

| Key | Classification and source |
| --- | --- |
| D | **Declared:** `inventory.yml`, `gitops/apps/*.yaml`, `gitops/bootstrap/root-app.yaml`, `gitops/manifests/`, `helm/values/`, application chart values/templates and `apps/immich/manifests/` in this checkout; not proof of deployment |
| H | **Live hosts:** authorized `control` SSH with existing `id_rsa_control`, `BatchMode=yes`, `StrictHostKeyChecking=yes`, `UpdateHostKeys=no`, 5s connect timeout and 25–35s command timeout; `hostname`, `uname`, selected OS/CPU/memory/root-filesystem fields, `pveversion`, `pvecm status`, `qm list`, `pct list`, `pvesm status`, allowlisted guest capacity/storage fields |
| G | **Live k3s guests:** existing authorized `ubuntu` SSH with the same trust/timeouts; `df -h /`, service active status, `sudo -n /usr/local/bin/k3s etcd-snapshot ls` on control planes |
| K | **Live API:** `/home/wsl/.local/bin/kubectl --kubeconfig /home/wsl/.kube/atlas-admin.yaml --request-timeout=15s`; `get nodes,ns,pods,deploy,sts,ds,job,cronjob,svc,ingress,pvc,pv,sc,certificate,clusterissuer,application,networkpolicy,middleware,resourcequota,limitrange,pdb,helmchart,cluster.postgresql.cnpg.io`, `top nodes`, warning-event metadata and `/readyz?verbose`; only relevant non-secret fields retained |
| N | **Live DNS/HTTP:** `dig +time=2 +tries=1 +short @10.0.0.10 docs.atlas.lan` and `pihole.atlas.lan`; bounded `curl -k` GET to docs through node `.110`, response status only; `pihole -v` and FTL service status over H SSH |
| B | **Live recovery metadata:** `pvesh get /cluster/backup` and `/cluster/ha/resources` returned empty arrays on Turing and Memex; G lists local etcd snapshots; K lists completed backup Job and CronJob status; no backup contents read |
| P | **Historical:** dated claims in AGENTS, old architecture/control-plane snapshots, and the Immich rollout runbook; not independently live-verified unless paired with another key |
| U | **Unavailable/unverified:** explicit limitation, not an absence claim |

No new SSH keys were accepted, no Secret objects or configuration/environment
dumps were read, no personal application records were inspected, and no runtime
changes, commits, pushes or tags were performed. Proxmox inspection used SSH's
local `pvesh` read endpoints; authenticated external API credentials were not
retrieved. Inventory coverage is nine entries: six baremetal hosts, hermes,
Pi-hole and localhost. See [placement diagrams](architecture/placement.md).

## Hosts and failure domains

All six `.101–.106` hosts are **observed Proxmox VE 9.2.9**, Debian 13,
kernel `7.0.14-8-pve` (H). Minsky is not merely an Ubuntu host as the old
architecture implied. Capacities below are usable OS memory, rounded GiB;
CPU means host logical CPUs, not guest allocation. Root disk and thin-pool
usage are distinct from guest/NAS filesystem usage.

| Inventory entry / address | Live role, grouping and guests | CPU / memory | Root size / used; local-lvm used | Health and gaps (H unless noted) |
| --- | --- | --- | --- | --- |
| turing / 10.0.0.101 | Atlas cluster; VM 201 | i5-6500, 4 / 15.50 GiB | 67.73 GiB / 15.82%; 16.88% | Online, ~6.1 GiB memory used, no swap used; node-exporter active |
| hopper / 10.0.0.102 | Atlas cluster; VM 202 | i5-6500, 4 / 15.50 GiB | 67.73 GiB / 15.87%; 9.56% | Online, ~6.0 GiB used, no swap used; node-exporter active |
| lovelace / 10.0.0.103 | Atlas cluster; VM 203 | i5-6500, 4 / 15.50 GiB | 66.35 GiB / 16.04%; 14.41% | Online, ~6.2 GiB used, no swap used; node-exporter active |
| babbage / 10.0.0.104 | Atlas cluster; VM 204 | i5-6500T, 4 / 15.50 GiB | 67.73 GiB / 15.82%; 34.97% | Online, ~8.0 GiB used, no swap used; node-exporter active |
| memex / 10.0.0.105 | Standalone PVE; VMs 100, 102, 9000 and LXC 63008 | Intel N150, 4 / 15.36 GiB | 93.94 GiB / 13.78%; 23.30% | No Corosync config; ~14.1 GiB used, ~1.26 GiB available, ~3.98 GiB swap used; node-exporter inactive |
| minsky / 10.0.0.106 | Standalone PVE; VM 94266 | Ryzen Embedded R2544, 8 / 15.33 GiB | 93.94 GiB / 9.98%; 14.06% | No Corosync config; ~10.7 GiB used, no swap used; node-exporter inactive |
| hermes / 10.0.10.1 | Declared service host; VM 94266 named hermes on Minsky | Guest configured 4 vCPU / 12 GiB, 64 GiB disk (H); Ubuntu 22.04.5 (H) | `control` SSH reachable | Static address; VM running is not guest-service health; exposed services and recovery U |
| pihole / 10.0.0.10 | Live Debian 12 DNS LXC 63008 on Memex | 1 configured core / 256 MiB + 256 MiB swap, 4 GiB rootfs | Guest root ~22% used; ~42 MiB RAM used | FTL active; Core 6.4.3, Web 6.6, FTL 6.7.1 (N); single resolver; DHCP/client adoption U |
| wsl_local / 127.0.0.1 | Local administrative workstation; WSL2, not PVE (local H) | Ryzen 7 5800X exposed as 16 CPUs / 15.58 GiB | ~1007 GiB root / ~29% used | Kernel `6.18.33.1-microsoft-standard-WSL2`; kubectl/SSH collection succeeds; Windows-host capacity/backup/metrics U |

The **Atlas Proxmox cluster has four members**, not six: `.101–.104`, all
online, secure Corosync authentication on, four votes, quorum three, Quorate
Yes (H). This quorum is separate from k3s etcd's two-of-three requirement.
All six hosts' `local` and `local-lvm` stores were active. No Ceph/shared PVE
storage was observed in `pvesm status`. This does not audit hardware RAID,
SMART, firmware, firewall rules, all mounts or out-of-band management (U).
Turing/Memex list no configured cluster backup jobs or HA resources (B);
Minsky's backup/HA configuration was not collected (U).

## Every observed Proxmox guest

`qm list` and `pct list` on each reachable host account for **eight VMs
(including one template) and one LXC** (H). Only Memex had an LXC. The
four-member cluster resource index also carried `qemu/100` on Memex with
`status=unknown`, despite Memex being standalone. Direct Memex evidence shows
it running; treat the index entry as stale/foreign metadata, not cluster
membership or guest failure.

| Host / kind / ID | Name and live power state | Configured capacity/storage (H) | Guest role, dependencies and evidence gaps |
| --- | --- | --- | --- |
| Turing / VM / 201 | atlas-k3s-cp1, running | 2 vCPU, 4 GiB, 40 GiB local-lvm | `.110`, k3s server/etcd; Ubuntu 24.04.4 and containerd 2.3.2-k3s2 (K/G) |
| Hopper / VM / 202 | atlas-k3s-cp2, running | 2 vCPU, 4 GiB, 40 GiB local-lvm | `.111`, k3s server/etcd; same OS/runtime (K/G) |
| Lovelace / VM / 203 | atlas-k3s-cp3, running | 2 vCPU, 4 GiB, 40 GiB local-lvm | `.112`, k3s server/etcd; same OS/runtime (K/G) |
| Babbage / VM / 204 | atlas-k3s-worker1, running | 2 vCPU, 6 GiB, 60 GiB local-lvm | `.113`, k3s agent; same OS/runtime (K/G) |
| Memex / VM / 100 | truenas, running | 4 vCPU, 16 GiB, 64 GiB local-lvm boot + four ~9314 GiB passed-through disks | NAS `.26` (D/K); live NFS consumers K. `control@10.0.10.26` rejected public-key auth; NAS version/pool health/free space/export permissions/snapshots U |
| Memex / VM / 102 | homeos, stopped | 2 vCPU, 2 GiB, 21.5 GiB local-lvm | Historical home automation guest; OS/app versions and reason for stopped state U; not the live Kubernetes Home Assistant |
| Memex / VM / 9000 | ubuntu-cloud-init-template, stopped, template=1 | 2 vCPU, 2 GiB, 3.5 GiB local-lvm base disk | Rebuild source, not a running service; template OS/image age and validation U |
| Minsky / VM / 94266 | hermes, running | 4 vCPU, 12 GiB, 64 GiB local-lvm | Static `.1`; SSH reachable; Ubuntu 22.04.5; exposed services and recovery U |
| Memex / LXC / 63008 | pihole, running, unprivileged=1 | 1 core, 256 MiB memory/swap each, 4 GiB local-lvm | Bridge vmbr0, `.10/24`, gateway `.1` (allowlisted H); DNS N; container firewall/backup/restore U |

TrueNAS's configured 16 GiB exceeds Memex's usable host RAM before PVE and
Pi-hole overhead. The observed swap pressure makes Memex a coupled DNS/storage
failure domain; running VMs do not prove the NAS is healthy. No VM snapshots,
guest backups or restores were tested. VM power state alone establishes neither
OS nor application availability.

## k3s capacity, placement and health

Four Ready nodes run **v1.36.3+k3s1**, Ubuntu 24.04.4,
kernel `6.8.0-136-generic`, containerd `2.3.2-k3s2` (K). The API VIP is
`https://10.0.0.108:6443`; `/readyz?verbose` passed including etcd (K).
All nodes have no taints: **control planes do run ordinary workloads**.
API HA does not make each application HA.

| Node / physical host | API-reported capacity | `top nodes` CPU / memory | Guest root use (G) |
| --- | --- | --- | --- |
| cp1 / Turing | 2 CPU, 3.76 GiB | 134m / 2655 MiB (68%) | 60%, ~16 GiB available |
| cp2 / Hopper | 2 CPU, 3.76 GiB | 234m / 2692 MiB (69%) | 33%, ~26 GiB available |
| cp3 / Lovelace | 2 CPU, 3.76 GiB | 259m / 2640 MiB (68%) | 49%, ~20 GiB available |
| worker1 / Babbage | 2 CPU, 5.72 GiB | 430m / 2435 MiB (41%) | **84%, ~9.7 GiB available** |

Total reported capacity is 8 CPUs/~17 GiB, distinct from 18 GiB configured VM
RAM. Historical 25–35% usage and worker-only scheduling descriptions are not
current. Historical memory-limit overcommit percentages were not remeasured
(U); current usage is not a sum of requests/limits. No ResourceQuota or
LimitRange objects were returned (K).

## All 17 observed namespaces and workloads

Placement uses cp1/cp2/cp3/worker1 abbreviations above. Versions are live
container image tags (K), not independently queried binaries. Every Deployment
had its desired ready replicas, every StatefulSet was 1/1 and every DaemonSet
had all desired instances ready. Empty below means no observed pods or workload
controllers, not an assertion that the namespace contains no objects.
Ingress and storage details are in the following sections; no omitted namespace
has an observed ingress or PVC.

| Namespace | Workloads/version and live placement (K) | Dependencies, health and recovery observations |
| --- | --- | --- |
| 3f-app | API + web `v0.1.1`, 1 replica each on cp2 | Private registry, Traefik/TLS; no PVC. Old web pod on cp1 is Error; active Deployment ready. Development-mode identity switcher is not authentication (D) |
| argocd | Application controller STS cp3; repo-server cp3; server, ApplicationSet controller, Redis cp2. Argo `v3.5.3`, Redis `8.6.4-alpine` | Reads forge main, renders/reconciles; ephemeral caches; 4 ingress NetworkPolicies. App status is not end-to-end service verification |
| cert-manager | Controller/webhook cp2, cainjector cp3, all `v1.21.2` | Internal CA signs TLS; one historical cainjector restart; issuer/cert status Ready. CA backup existence U |
| cnpg-system | cloudnative-pg `1.30.1`, cp1 | Owns Immich PostgreSQL Cluster/Database; one restart; webhook dependency; operator alone has no data PVC |
| dave-study | `v0.1.0`, two replicas cp1/cp3 | Private registry/static HTTP, no PVC; replica spread observed, failover not tested |
| default | No pods/controllers; Kubernetes API Service | Default namespace, not an application tenant |
| demo | No pods/controllers | Historical orphan/legacy namespace (P); no live application inferred |
| external-dns | `v0.23.0` + Pi-hole webhook `v1.0.0`, 2/2 containers on cp2 | Watches Ingress/Service → Pi-hole API; old Completed pod cp1 retained; health and DNS answers observed, authenticated write path not exercised |
| gitea | Gitea `1.27.0-rootless` cp2; PostgreSQL STS `17.6.0-debian-12-r4` cp3; runner STS `2.0.1` + restartable init dind `29.5.2` worker1 | Forge/registry/CI depend on NAS, DNS/CA and DB. All Ready; runner Argo drift persists; all three PVCs NFS. PostgreSQL volume-permissions init `os-shell:12-debian-12-r51`; bootstrap init uses Gitea image; runner bootstrap BusyBox 1.38.0 |
| home-assistant | `2026.9.4`, cp3; BusyBox 1.37.0 init | NFS config, Traefik/TLS, ingress NetworkPolicy and IP middleware. One replica; integrations/personal state intentionally not inspected |
| immich | Server `v3.2.0` cp1; ML `v3.2.0` worker1; Valkey `9.1-alpine` (digest pinned) cp2; CNPG PostgreSQL `18-standard-trixie` cp1 | CNPG Cluster 1 ready instance, healthy; server→DB/Valkey/ML/media. PostgreSQL local-path; other PVCs NFS; Valkey emptyDir. Daily dump/Restic `0.18.1` Job on cp1 succeeded at 02:00:12 UTC; contents/restore U |
| kube-node-lease | No pods/controllers | Node heartbeat leases, not a tenant workload |
| kube-public | No pods/controllers | Kubernetes system namespace |
| kube-system | CoreDNS `1.14.6` cp2; Traefik `3.7.8`, metrics-server `v0.9.0`, local-path provisioner `v0.0.36` cp1; NFS CSI `v4.13.4` controllers cp2/cp3 (2 replicas), node DS all four; kube-vip `v1.2.3` DS three control planes | DNS/API/ingress/storage substrate. ServiceLB `klipper-lb:v0.4.17` DS for Traefik, Grafana, Gitea SSH, each all four nodes. Four retained Helm installer Jobs succeeded (`klipper-helm:v0.13.3-build20260727`) |
| monitoring | Grafana `13.1.3` + two sidecars `2.10.1`, operator `v0.93.0`, kube-state-metrics `v2.19.1`, Prometheus `v3.13.2-distroless` + config-reloader `v0.93.0`, all worker1; node-exporter `v1.12.1-distroless` DS all four | Chart 88.3.0 via k3s HelmChart, not an Argo child. Grafana/Prometheus emptyDir; declared 7d retention, anonymous Viewer (D/P). Scrape target success and alerts not queried (U) |
| redop | API + worker `redop-api:sha-acbcee9` cp1; cockpit same tag cp2; UI same tag cp3; Postgres `16.4-alpine` cp3; migration Job same API tag cp1 succeeded | API/worker→shared DB; cockpit→API; API→data PVC; middleware internal-only. Prior API pod Unhealthy event at 02:50:13 UTC; current pods Ready, zero restarts. Checkout declares `sha-de44d86`, so local/live revision differs, despite Argo Synced to forge |
| sealed-secrets | controller `0.40.0` cp3 | Unseals Git-managed secrets; key backup/restore U. Ready does not verify every sealed object; chart appVersion mismatch is historical packaging, not live controller version |

NFS CSI auxiliary images are provisioner `v6.3.0`, resizer `v2.2.0`,
snapshotter `v8.6.0`, livenessprobe `v2.19.0` and node registrar `v2.17.0` (K).
The snapshotter image does not prove snapshots or backup policy exist.
CNPG uses the `1.30.1` operator bootstrap image and PostgreSQL 18 for dump init;
Redop API's migration-wait init uses its API image (K).

## All declared and observed Argo Applications

All 14 live Applications use project `platform`, the same cluster destination,
and forge repository `http://gitea-http.gitea.svc.cluster.local:3000/atlas-admin/atlas.git`
on `main`. At collection they compared to Git revision **`2a08871434711058d63780937ad096eaa03ccda3`** (K).
Local declarations are a separate evidence source (D), not the forge branch
contents. Multi-source apps take chart pins plus `$values` from forge main.

| Application | Declaration path/pin (D), live source consistent unless noted | Destination | Live state (K) |
| --- | --- | --- | --- |
| root | `gitops/bootstrap/root-app.yaml` → `gitops/apps` | argocd | Synced / Healthy |
| atlas-config | `gitops/apps/atlas-config.yaml` → `gitops/manifests` | cert-manager | Synced / Healthy; raw CA, DNS, storage and platform resources |
| argocd | `gitops/apps/argocd.yaml`, argo-cd 10.9.6 | argocd | Synced / Healthy |
| cert-manager | `gitops/apps/cert-manager.yaml`, v1.21.2 | cert-manager | Synced / Healthy |
| cloudnative-pg | `gitops/apps/cnpg.yaml`, 0.29.1 | cnpg-system | Synced / Healthy; sync-wave -1 declared |
| external-dns | `gitops/apps/external-dns.yaml`, 1.23.0 | external-dns | Synced / Healthy |
| gitea | `gitops/apps/gitea.yaml`, 12.7.0 | gitea | Synced / Healthy |
| gitea-actions | `gitops/apps/gitea-actions.yaml`, actions 0.1.2 | gitea | **OutOfSync / Healthy**, resource `StatefulSet/gitea-actions-runner`; field-level cause not re-established |
| sealed-secrets | `gitops/apps/sealed-secrets.yaml`, 2.5.19 | sealed-secrets | Synced / Healthy |
| immich | `gitops/apps/immich.yaml`, OCI chart 0.13.2 + `apps/immich/manifests` | immich | Synced / Healthy |
| redop | `gitops/apps/redop.yaml` → `apps/redop/chart` | redop | Synced / Healthy against forge, not proof local tag is deployed |
| 3f-app | `gitops/apps/3f-app.yaml` → `apps/3f-app/chart` | 3f-app | Synced / Healthy |
| dave-study | `gitops/apps/dave-study.yaml` → `apps/dave-study/chart` | dave-study | Synced / Healthy |
| home-assistant | `gitops/apps/home-assistant.yaml` → `apps/home-assistant/chart` | home-assistant | Synced / Healthy |
| docs | Uncommitted publishing-layer `gitops/apps/docs.yaml` → `apps/docs/chart` | docs | **Declared only:** no live Application, namespace, workload, ingress or certificate |

The four live k3s HelmCharts are `atlas-monitoring` 88.3.0,
`csi-driver-nfs` 4.13.4, `traefik` and `traefik-crd` bundled
`40.1.4+up40.1.0` (K). They must remain in the platform inventory even though
there is no monitoring/CSI/Traefik Argo Application.

## Ingress, DNS and trust

Every observed Ingress is class `traefik`, with an `atlas-ca` Certificate Ready
(K). Leaf expiries span **2026-12-31 through 2027-01-05**; root CA Certificate
expires 2036-09-29. Both `atlas-ca` and `atlas-selfsigned-bootstrap` issuers
report Ready. Secret values/private keys were not read. Ready cert status is
not proof client CA trust, TLS verification or successful application login.

| Host(s) | Routes → Service port (K) | TLS Certificate |
| --- | --- | --- |
| git.atlas.lan, registry.atlas.lan | `/` → gitea-http:3000 | gitea-tls |
| argocd.atlas.lan | `/` → argocd-server:80 | argocd-server-tls |
| 3fapp.atlas.lan | `/api`, `/docs`, `/redoc`, `/openapi.json`, `/health` → API:8000; `/` → web:5173 | 3f-app-tls |
| dave-study.atlas.lan | `/` → dave-study:80 | dave-study-tls |
| home-assistant.atlas.lan | `/` → home-assistant:8123 | home-assistant-tls |
| immich.atlas.lan | `/` → immich-server:2283 | immich-tls |
| redop.atlas.lan | `/red` → API:8000; `/screens` → UI:3000; `/api/backend`, `/` → cockpit:3000 | redop-tls |
| docs.atlas.lan | No live route; bounded GET through `.110` returns **404** (N) | None observed |

Traefik LoadBalancer publishes ports 80/443 on `.110–.113`; Gitea SSH
LoadBalancer uses 2222 (NodePort 31433); Grafana uses **HTTP 3000** (NodePort
32688), with no Grafana Ingress (K). Other Services are internal ClusterIP,
including PostgreSQL 5432, Valkey/Redis 6379, ML 3003, Prometheus 9090,
Argo repo-server 8081 and ApplicationSet webhook 7000. Monitoring scrape
Services also expose CoreDNS 9153, controller 10257, scheduler 10259,
proxy 10249, etcd 2381 and kubelet metrics (K); target availability U.

Pi-hole `.10` answered `pihole.atlas.lan` with `.10` and `docs.atlas.lan`
with all four node IPs (N). This supports the wildcard DNS design, **not a
docs deployment** or proof of ExternalDNS authenticated writes. ExternalDNS
live containers are Ready (K); `registry: noop`, `policy: upsert-only`,
one-minute interval and `atlas.lan` domain filter are declared (D). Stale
records are expected on deletion. CoreDNS custom routing is declared in
`gitops/manifests/coredns-atlas.yaml`; in-cluster lookup and current ConfigMap
contents were not separately checked (U). Router DHCP, tailnet DNS policy,
remote reachability and client trust were not inspected. ADR 0001's direct
Pi-hole tailnet-agent design differs from the later Memex subnet-route/split-DNS
runbook; neither tailnet configuration was established live in this review.

## Every observed persistent claim

All ten PVCs were Bound (K), totaling **219 GiB requested**: 209 GiB NFS and
10 GiB local. Requests are not used space or guaranteed NFS quota. All observed
PVs and both classes use **Delete** reclaim; deletion can lose data.

| Namespace / claim | Capacity / access / class | Consumer, placement and recovery |
| --- | --- | --- |
| gitea / gitea-shared-storage | 10 GiB / RWO / truenas-nfs | Gitea cp2; repositories/packages; restore consistency with DB required |
| gitea / data-gitea-postgresql-0 | 8 GiB / RWO / truenas-nfs | PostgreSQL cp3; DB backup/restore U |
| gitea / data-runner-gitea-actions-runner-0 | 1 GiB / RWO / truenas-nfs | Runner worker1; registration/state; backup U |
| home-assistant / home-assistant-config | 10 GiB / RWX / truenas-nfs | Home Assistant cp3; config/history backup U |
| immich / immich-library | 50 GiB / RWX / truenas-nfs | Server cp1; media not protected by DB dumps |
| immich / immich-machine-learning | 10 GiB / RWX / truenas-nfs | ML worker1; model cache; independent from media |
| immich / immich-backup | 100 GiB / RWX / truenas-nfs | Daily DB dump/Restic Job cp1; same NAS as media, not independent disaster protection |
| immich / immich-database-local-1 | 10 GiB / RWO / local-path | Single DB primary cp1; PV node affinity cp1; off-node recovery relies on logical dumps |
| redop / redop-data | 10 GiB / RWO / truenas-nfs | API cp1; shell/vector/episodic state (D); backup U |
| redop / redop-postgres-data | 10 GiB / RWO / truenas-nfs | DB cp3; backup/restore U |

`truenas-nfs` uses `nfs.csi.k8s.io`, server `10.0.10.26`, export
`/mnt/data/atlas-k8s`, per-namespace/PVC subdirectory, Immediate binding and
expansion allowed (K). Default `local-path` uses `rancher.io/local-path` and
WaitForFirstConsumer. NFS makes volume mounts movable, not the single-writer
databases replicated. Prometheus, Grafana, Argo caches and Valkey are ephemeral
(K); retention/settings recovery requires declarations and/or external backups.

## Security, drift and recovery findings

| Evidence / finding | Impact and remaining proof |
| --- | --- |
| H: Memex ~92% used memory, ~4 GiB swap; TrueNAS allocated 16 GiB on ~15.36 GiB host | DNS and all NFS-backed services share this pressure/failure domain; NAS health and backup proof unavailable |
| G/K: worker root 84% used; control-plane memory ~68–69% | Capacity margin needs operator attention; no cleanup/resize performed; no sustained-load or pressure-event analysis |
| K: all nodes schedulable, most app components on control planes; single DB/forge/ingress replicas | Node or host loss can interrupt services despite API quorum; failover not tested |
| B/G: five recent local etcd snapshots per control plane (plus cp1 bootstrap snapshot) | Local restore candidates exist, but off-host copies, integrity and restore rehearsal U; snapshots do not back up application PVCs |
| B: Turing/Memex backup and HA resource lists empty | No configured jobs/resources there; manual/external backups remain U, not proven absent everywhere |
| K/D/P: Immich scheduled Job succeeded; P records an earlier one-off Restic snapshot | One scheduled completion is new evidence, not snapshot contents, retained history or successful restore; no pod exec or temporary recovery pods created |
| K: six NetworkPolicies: four Argo ingress policies, Gitea PostgreSQL, Home Assistant ingress | No observed namespace-wide default deny elsewhere; DB policy permits port 5432 without a source selector and unrestricted egress; enforcement not tested |
| K/D: 3f-app, Redop, Home Assistant middleware allows 10.0.0.0/8 | Broad internal network access, not user authentication. 3f-app development mode and Redop cockpit disabled auth are declared; do not infer production isolation |
| K/D/P: privileged host-network/hostPath platform agents, CI dind and shared GitOps project | High-trust administration/CI boundary; RBAC, encryption-at-rest configuration, firewall and credential rotation not audited. Sealed Secrets protects Git ciphertext, not automatically every live Secret in etcd |
| K: Grafana LoadBalancer HTTP 3000; D/P anonymous Viewer | Metrics can expose operational details to reachable clients; live auth settings/client restrictions not inspected |
| K: gitea-actions Healthy / OutOfSync | Only STS resource drift established; historical API-defaulting explanation is a hypothesis here, not a fresh diff verification |
| D/K: checkout Redop tag sha-de44d86 versus live sha-acbcee9 | Argo Synced refers to forge revision, not this unpushed checkout; no promotion/remediation authorized |
| N/K versus P: Pi-hole `.10` running and ExternalDNS deployed | AGENTS `.107`/empty-namespace claims are stale; healthy containers/DNS do not prove all records correct or router cutover |
| N/K: docs wildcard resolves, HTTP 404, no app/namespace/ingress | Live site gate blocked: authorization, CI/registry prerequisites, first immutable image promotion and namespace pull-secret provisioning still required; see publishing runbook |

Recovery order is **physical host/storage and trusted access → etcd/API/DNS →
CA and Sealed Secrets keys → forge database/repositories/registry → Argo
bootstrap → applications and data**. Forge and Argo run on the cluster they
restore: a separate copy of this repository, verified images, credentials and
key backups are necessary to break that dependency. Follow the
[control-plane](kubernetes-control-plane.md), [GitOps](gitops-platform.md),
[secret-key](sealing-secrets.md) and [Immich](runbooks/immich.md) runbooks with
fresh authorization; no recovery action was run by this review.

## 2026-10-11 sync remediation and refresh

A follow-up collection (workstation clock 2026-10-11 ~02:10 UTC) fixed the
drift above and re-collected the affected inventory. Changes were made through
git (commits `b9657a0`, `a0b6b35` on the forge); nothing was applied imperatively
except the four k3s guests' own DNS resolver settings, which are host
configuration outside the cluster's GitOps scope.

**Root cause of the 2026-10-10/11 image-pull outage (K/G/H):** the k3s guests'
resolvers pointed at the router (`10.0.0.1`), which answered no `atlas.lan`
names, so node containerd could not resolve `registry.atlas.lan`. The CoreDNS
`coredns-custom` `atlas.lan` server block also had no upstream, so in-cluster
clients could only resolve the four hardcoded host entries. Fixes:

- `gitops/manifests/coredns-atlas.yaml` now adds `forward . 10.0.0.10` inside
  the `atlas.lan` server block; unknown `atlas.lan` names forward to Pi-hole
  (K: live ConfigMap verified after `atlas-config` hard refresh).
- All four k3s guests (VMs 201–204) had `qm ... --nameserver` set to
  `10.0.0.10`, `/etc/netplan/50-cloud-init.yaml` updated and applied in-guest,
  and the cloud-init role default `dns_server` changed to `10.0.0.10` (H + D).
  Verified: `getent` resolves `registry.atlas.lan` on every guest; an in-pod
  lookup from `redop-api` resolves it to the Traefik ClusterIP (K).

**Resulting Argo state (K):** every Application is `Synced / Healthy`, including
`redop` (its `redop-migrate` PreSync hook had looped on image pulls; it now
completed in 52s and the live tag is `sha-54aa2c7`, matching this checkout),
`gitea-actions` (the ignoreDifferences was replaced with explicit JSON pointers
for the API-defaulted/Helm-era StatefulSet fields, verified against the Argo
managed-resources diff), and `docs` (its `ImagePullBackOff` pod pulled and
reached Ready once DNS worked).

**Counts after this refresh (K):** 21 namespaces (adds `atlas-landing`,
`docs`, `odysseus`, `photocraft` to the 17 above), 19 live Applications (adds
`atlas-landing`, `docs`, `odysseus`, `photocraft`, `gitea-runner-hygiene` to the
14), 11 Ingresses (adds `atlas.lan`/`www.atlas.lan`, `docs.atlas.lan`,
`odysseus.atlas.lan`, `photocraft.atlas.lan`), and 14 bound PVCs totaling
251 GiB requested (the four `odysseus` claims add 32 GiB NFS). New live
workloads: `atlas-landing v0.2.0` (cp3), `docs` (immutable digest image, cp1),
`photocraft v0.6.1` (worker1), and `odysseus` (main app, ChromaDB `1.0.20`,
ntfy `v2.11.0`, searxng digest-pinned — all on worker1 per its pin). `dave-study`
now runs `v0.2.2` on worker1/cp3.

**Other live observations (K/G/H):** node kernel is now `6.8.0-146-generic`;
guest root use is cp1 44% (50G), cp2 49% (38G), cp3 **74%** (38G), worker1 28%
(58G — the worker's 84% finding is resolved by the resize). `kubectl top`
shows control-plane memory 25–30% and worker 49% after the 4 vCPU/12 GiB
resize. Monitoring retains two `Failed` Grafana pods from superseded
ReplicaSets (harmless leftovers; the Deployment is 1/1). `docs.atlas.lan`
resolves via Pi-hole and returns **HTTP 200** through node `.110`, with a Ready
`atlas-ca` certificate — the 404/no-ingress finding above is superseded.

## Access gaps and completion boundary

- Agent SSH `.155` timed out; TrueNAS `.26` SSH denied the authorized key.
  No password fallback, new key enrollment or credential retrieval was attempted.
- All reachable PVE hosts and their enumerated guests are accounted for, but
  stopped guests/templates were not booted; their OS/app state remains U.
- Hardware health, NAS pool/version/capacity, backup contents/off-site copies,
  restore rehearsals, external auth/RBAC audits, DHCP and tailnet configuration,
  all endpoint logins and monitoring target health remain unavailable/unverified.
- The observed warning-event list retained one old Redop probe failure; events
  expire, so this is not an incident history. Old Error/Completed pods are
  distinguished from currently ready controllers.
- Publishing artifacts were already partial/uncommitted and were not changed
  here. No live publishing success is claimed. [Publishing gates](docs-publishing.md)
  must be satisfied by a separately authorized release.

## Local validation handoff

Validation found **43 diagrams**, all at most five elements.
All rendered successfully with temporary Mermaid CLI 11.12.0 outside the
checkout. Source coverage checks matched nine inventory addresses, all 17 live
namespaces, 14 live Applications and ten PVCs; the pinned docs environment
matched all 29 dependency versions.

Subsequent local verification passed the strict MkDocs build of a
clean intended-release source, excluding the unrelated backlog and six pending
specs. The out-of-tree Pi-hole runbook link was corrected to a published target;
the built site has no broken internal links/anchors and a populated search index.

Browser verification of the built site's existing Material integration found
all 43 diagrams rendered, each with at most five elements, and no page/asset
errors. The earlier empty-container/timeout diagnosis is superseded: Material
renders SVGs inside closed shadow roots, so checking only host HTML misses them.
The verification retained those roots through `attachShadow` instrumentation;
standalone rendering alone is still insufficient. Mermaid remains CDN-dependent,
so local success does not establish offline availability or live deployment.
The live observation was blocked at collection: no docs ingress
and HTTP 404. Superseded on 2026-10-11: the docs Application, ingress and
certificate are live and `https://docs.atlas.lan/` returns 200 (see the
2026-10-11 refresh above).
