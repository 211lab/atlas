# Home Assistant self-hosting specification

## Goal

Document the developer/operator design for self-hosting Home Assistant on the Atlas K3s cluster through the existing Argo CD GitOps workflow, so a future implementation is available to the home LAN and retains its configuration across pod restarts.

## User-visible behavior

- A home-LAN user can open `https://home-assistant.atlas.lan` and use Home Assistant's web UI.
- Home Assistant configuration and state survive pod restarts and rescheduling.
- Argo CD reconciles the deployment from the repository; access uses Atlas internal TLS and existing LAN ingress conventions.
- Developers can find a focused guide describing the proposed architecture, repository touchpoints, implementation/validation workflow, and operational limits without confusing planned behavior for a live deployment.

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
4. **Safe application access** — Given requests arrive through the configured ingress, then Home Assistant is configured to trust only the intended reverse proxy path as required for forwarded headers; it is not exposed by an additional unprotected service/ingress.
5. **Render validation** — Given the selected chart/manifests and values, when YAML and chart rendering validation run, then they render successfully and include the expected ingress and persistent volume claim.
6. **Runtime check** — Given the GitOps deployment has synced, when tested from the home LAN, then the UI responds over HTTPS and configuration remains after a pod restart.
7. **Developer guide** — Given a contributor starts implementation, when they read `docs/home-assistant.md`, then it explains the scope, proposed components and repository conventions, safe rollout/rollback, validation steps, and outstanding hardware/storage checks; it clearly identifies the deployment as planned until the GitOps resources exist and are verified.

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

## Plan

1. Add `docs/home-assistant.md` as a developer/operator guide based on existing Atlas GitOps, ingress, storage, and validation conventions; distinguish documented intent from deployed state.
2. Link the guide from `README.md` and keep this spec as the acceptance source for any later deployment implementation.
3. Validate Markdown links and commands against repository conventions; do not create Kubernetes resources or claim runtime deployment in this documentation-only change.

## Rollback

Revert the documentation and README link in Git. This docs-only change creates no workloads or persistent resources; a later deployment rollback must stop Argo CD management while retaining the PVC and underlying configuration until deletion is explicitly approved.

## Open questions / rollout checks

- Confirm whether any intended integrations need Zigbee/Z-Wave USB adapters, Bluetooth, multicast discovery, host networking, or other host-level access before relying on the K3s deployment.
- Confirm `truenas-nfs` capacity and backup/restore procedure for the Home Assistant configuration.
- Verify actual chart/manifests support the required ingress and proxy configuration before implementation.
- Runtime acceptance requires access to the live cluster and an allowed home-LAN client.
