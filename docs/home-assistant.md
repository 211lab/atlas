# Home Assistant on Atlas (planned)

> **Status: planned, not deployed.** No Home Assistant Argo CD Application, chart, workload, ingress, or PVC exists in this repository today. This guide records a proposed design; it is not evidence of a running service.

## Scope

The proposed service is a single-replica Home Assistant Container workload on Atlas K3s, managed by the existing Argo CD app-of-apps, with persistent configuration and LAN-only HTTPS access at `https://home-assistant.atlas.lan`.

In scope: network-based integrations that work with ordinary Kubernetes networking, the existing Traefik ingress, internal `atlas-ca` TLS, a `truenas-nfs` configuration PVC, and an ingress middleware restricting clients to `10.0.0.0/8`.

Out of scope: public access or remote access, Home Assistant OS and add-ons, USB/Zigbee/Z-Wave radios, Bluetooth, host networking, and multicast/mDNS bridging. Integration setup, automations, dashboards, and device configuration are also not part of this repository design task.

## Proposed architecture

- An Argo CD `Application` in `gitops/apps/` targets a dedicated Home Assistant namespace. It follows the root app-of-apps, automated sync, and self-heal conventions in [GitOps platform](gitops-platform.md).
- Choose either an in-repository chart at `apps/home-assistant/chart/` or a pinned external chart with values at `helm/values/home-assistant.yaml`. Keep chart versions pinned and configuration reviewable in Git; verify the chosen chart can express the ingress, proxy, and PVC requirements before implementation.
- Run one replica only. Mount a persistent claim for Home Assistant's configuration directory, using `storageClassName: truenas-nfs`. Do not rely on the container filesystem for configuration/state. No separate database is proposed.
- Route the web UI through the existing Traefik ingress for `home-assistant.atlas.lan`; request a certificate from cert-manager issuer `atlas-ca`. Attach the repository's LAN IP-allowlist middleware policy for `10.0.0.0/8`. Do not add another unprotected ingress or service exposure.
- Configure Home Assistant's trusted-proxy/forwarded-header settings narrowly for the actual ingress path. Determine the appropriate proxy address/range from the deployed Traefik topology during implementation; do not trust arbitrary forwarded headers. Validate the chosen chart supports this configuration.

The hostname, allowlist, CA issuer, and storage class are assumptions based on current repository conventions, not newly verified runtime facts. Confirm the hostname and DNS behavior with the operator. Confirm intended integrations do not require multicast discovery, USB radios, Bluetooth, host networking, or other host-level access. Confirm NFS capacity and a tested backup/restore procedure before relying on it for configuration data.

## Repository conventions and implementation workflow

1. Review `docs/gitops-platform.md`, particularly the app-of-apps, chart/values layout, ingress conventions, and storage notes. Existing in-repo middleware examples include `apps/3f-app/chart/templates/middleware-ipallow.yaml`; use the established policy rather than inventing a broader allowlist.
2. Select and pin a chart or create a focused local chart. Add its `gitops/apps/<name>.yaml` Application and required chart/values only when implementation is approved. Use the existing namespace, automated sync, and self-heal patterns. Keep secrets out of plaintext Git; use the documented Sealed Secrets workflow if secrets become necessary.
3. Render and inspect locally before merge. Suggested checks, adjusted to the selected chart and available tools:

   ```sh
   helm lint apps/home-assistant/chart
   helm template home-assistant apps/home-assistant/chart --namespace home-assistant
   kubectl apply --dry-run=client -f gitops/apps/home-assistant.yaml
   ```

   For an external chart, render its pinned version with `helm template` and the repository values file instead. Check rendered resources for one replica, the expected PVC/storage class, ingress hostname and TLS issuer, allowlist middleware attachment, and proxy trust configuration. Run repository CI and applicable YAML/lint checks as well.
4. Merge through the normal GitOps review flow and observe Argo CD sync/health before attempting runtime checks. Do not claim runtime acceptance based solely on rendering.

## Rollout, validation, and rollback

Before rollout, verify DNS for `home-assistant.atlas.lan`, `atlas-ca` issuance, Traefik middleware behavior, the `truenas-nfs` provisioner/export, available capacity, and a documented recoverable backup. Roll out via the Argo CD Application; do not bypass Git as the source of truth for routine changes.

Development validation can cover chart lint/rendering, YAML validity, resource shape, and GitOps Application configuration. Runtime validation requires cluster access and an allowed LAN client: confirm Argo CD sync and pod readiness, PVC binding/mount, HTTPS certificate and UI response from `10.0.0.0/8`, denial from outside the allowlist, and configuration persistence after a controlled pod restart. Test integrations individually on the LAN; ordinary cluster rendering cannot prove discovery or device connectivity.

To roll back an application change, revert the Git change and let Argo CD reconcile. For a later deployed instance, stop Argo CD management / remove the Application without deleting the PVC or backing NFS data; retain configuration until recovery or deletion is explicitly approved. Restore from the verified backup if data recovery is needed. This documentation-only change creates no workload or persistent resources.

## Operational limitations and open checks

- One replica is intentional: this design does not provide HA or concurrent writers.
- NFS is proposed for a single-writer configuration directory, but filesystem/locking behavior and Home Assistant suitability must be validated. Capacity, retention, backup cadence, and restore steps remain operator decisions.
- Kubernetes networking may not provide multicast/mDNS discovery, Bluetooth, USB radio access, or host-level integration capabilities. Those needs require a separate design decision and are outside this scope.
- No public access, Home Assistant OS, add-ons, SSO, or remote access is designed here.
- Confirm the actual host/DNS requirement, integration hardware and multicast needs, NFS capacity/backup/restore, chart capabilities, and trusted-proxy ranges before implementation.
