# Home Assistant self-hosting specification

## Goal

Deploy Home Assistant on the Atlas K3s cluster through the existing Argo CD GitOps workflow, and document the implementation so it is available to the home LAN and retains its configuration across pod restarts.

## User-visible behavior

- A home-LAN user can open `https://home-assistant.atlas.lan` and use Home Assistant's web UI.
- Home Assistant configuration and state survive pod restarts and rescheduling.
- Argo CD reconciles the deployment from the repository; access uses Atlas internal TLS and existing LAN ingress conventions.
- Developers/operators can find a focused guide describing the implemented architecture, repository touchpoints, validation and day-2 workflow, and operational limits, while distinguishing declared configuration from runtime verification.

## Non-goals

- Home Assistant OS, add-ons, or provisioning a dedicated VM.
- Public internet exposure, remote access, or SSO.
- USB/Zigbee/Z-Wave passthrough, Bluetooth, host networking, or multicast/mDNS bridging.
- Configuring integrations, importing an existing configuration, automations, dashboards, or client devices.
- Changing cluster, DNS, certificate, or storage infrastructure.

## Acceptance criteria

1. **GitOps deployment** — Given the root app-of-apps is reconciling, when this change is merged, then an Argo CD Application deploys Home Assistant in its own namespace with automated sync and self-heal.
2. **LAN HTTPS access** — Given a client on the allowed private LAN, when it visits `https://home-assistant.atlas.lan`, then the existing Traefik ingress routes to Home Assistant with an Atlas CA certificate and the configured LAN allowlist; clients outside the allowed range are denied.
3. **Persistent configuration** — Given the pod is restarted or rescheduled, when Home Assistant becomes ready, then its configuration/state remains available from persistent storage.
4. **Safe application access** — Given requests arrive at the Home Assistant pod, then a Kubernetes NetworkPolicy allows inbound port 8123 only from Traefik pods; the Home Assistant trusted-proxy CIDR covers the reschedulable Traefik pod address but other pods cannot connect through the policy; no other unprotected service/ingress is exposed.
5. **Render validation** — Given the selected chart/manifests and values, when YAML and chart rendering validation run, then they render successfully and include the expected ingress and persistent volume claim.
6. **Runtime check** — Given the GitOps deployment has synced, when tested from the home LAN, then the UI responds over HTTPS and configuration remains after a pod restart.
7. **Developer/operator guide** — Given a contributor or operator reads `docs/home-assistant.md`, then it describes the implemented paths and architecture, validation, safe rollout/rollback, and outstanding hardware/storage limitations; it does not claim runtime health unless checked against the live cluster.

## Constraints

- Follow the existing `gitops/apps/` Argo CD Application pattern and repository Helm/manifests conventions.
- Follow Atlas internal TLS (`atlas-ca`) and LAN-only ingress conventions.
- Use existing persistent storage conventions; do not store Home Assistant configuration only in the container filesystem.
- Do not commit credentials or other secrets in plaintext.
- Do not claim live runtime acceptance without access to the cluster and LAN.

## Assumptions

- ASSUMPTION: The selected runtime is Atlas K3s, per the user's choice, rather than Home Assistant OS in a VM.
- ASSUMPTION: `home-assistant.atlas.lan` is acceptable as the LAN hostname and resolves through current wildcard DNS conventions.
- ASSUMPTION: LAN-only access uses the repository's current Traefik `10.0.0.0/8` allowlist policy.
- ASSUMPTION: Existing `truenas-nfs` storage is suitable for Home Assistant's configuration directory. This is a small single-writer workload; confirm filesystem/locking behavior before production reliance. No database is added in this scope.
- ASSUMPTION: The initial use is network-based integrations only. Integrations needing LAN multicast discovery, USB radios, Bluetooth, or host networking are deferred; Kubernetes networking may not provide those capabilities transparently.
- ASSUMPTION: A conservative single-replica deployment is appropriate; backup policy, resource sizing, and any advanced integration needs remain operator follow-ups.
- ASSUMPTION: The Home Assistant HTTP proxy trust configuration will trust Atlas K3s pod source addresses (`10.42.0.0/16`) because Traefik's pod IP can change during rescheduling. The live pod CIDRs were observed on all four current nodes; review this trust boundary if cluster networking changes.
- ASSUMPTION: The cluster's NetworkPolicy controller enforces ingress policy for pods; confirm probe readiness and Traefik routing after sync.

## Plan

1. Add a pinned Home Assistant Container deployment chart under `apps/home-assistant/chart/`, with a single-replica Deployment, internal Service, HTTP-proxy bootstrap configuration, NFS-backed configuration PVC with prune/delete protection, LAN-only Traefik Ingress/middleware, Traefik-only NetworkPolicy, and `atlas-ca` TLS.
2. Add `gitops/apps/home-assistant.yaml` using the existing app-of-apps pattern.
3. Update `docs/home-assistant.md` and `README.md` with actual chart paths, implementation settings, rollout/validation and rollback steps, and verified live status only where checks support it.
4. Validate chart rendering and YAML; verify application fields, ingress allowlist/TLS, single replica, PVC, and proxy trust. Deploy through the GitOps main branch and perform LAN HTTPS/readiness/persistence checks; clearly list anything that remains blocked.

## Rollback

Revert the GitOps commit to remove the deployment from reconciliation. The PVC is explicitly protected from automatic prune/deletion; preserve the PVC and NFS data until the operator explicitly approves data removal. Re-apply the prior Git revision if rollback is needed without removing persistent data.

## Open questions / rollout checks

- Confirm whether any intended integrations need Zigbee/Z-Wave USB adapters, Bluetooth, multicast discovery, host networking, or other host-level access before relying on the K3s deployment.
- Confirm `truenas-nfs` capacity and backup/restore procedure before relying on it as the only copy of Home Assistant configuration.
- Runtime acceptance requires access to the live cluster and an allowed home-LAN client.
