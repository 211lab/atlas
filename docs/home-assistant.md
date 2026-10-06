# Home Assistant on Atlas

> **Status: GitOps implementation.** The Application targets `main`; check live Argo CD state and the validation steps below before relying on the service. This guide records desired configuration, not a guarantee of current cluster health.

## Architecture

The Home Assistant Container chart is at `apps/home-assistant/chart`; Argo CD configuration is `gitops/apps/home-assistant.yaml`. The Application targets namespace `home-assistant`, uses automated sync with prune and self-heal, and creates the namespace. The chart deploys one replica with `Recreate` strategy using `ghcr.io/home-assistant/home-assistant:2026.9.4`.

An init container copies the chart's default `configuration.yaml` to the writable configuration PVC only when the file is absent, assigning the new file to UID/GID 1000. The bootstrap config enables `default_config` and configures `http.use_x_forwarded_for` with `trusted_proxies: 10.42.0.0/16`. A NetworkPolicy limits inbound pod traffic on 8123 to Traefik pods, so only that proxy path can use forwarded headers. For Home Assistant 2026.9, HTTP configuration is migrated through the Home Assistant UI; follow the [HTTP integration documentation](https://www.home-assistant.io/integrations/http/) when changing proxy settings.

The service is ClusterIP on port 8123. Traefik ingress serves `home-assistant.atlas.lan`, requests the `atlas-ca` certificate, and attaches the middleware allowing `10.0.0.0/8`. A NetworkPolicy permits inbound port 8123 only from Traefik pods in `kube-system`; this bounds the wider trusted-proxy Pod CIDR. The `home-assistant-config` PVC requests 10Gi on `truenas-nfs` with RWX. Its `argocd.argoproj.io/sync-options: Prune=false,Delete=false` annotation prevents Argo CD pruning/deleting the claim. Note that the StorageClass reclaim policy is `Delete`; PVC protection is not a substitute for backup or explicit data-retention planning.

There is no external database, secret, or other credential configured. This scope does not provide radio/USB, Bluetooth, host-network, or multicast/mDNS integrations. It is a single instance, not HA.

See the official [Home Assistant Container installation](https://www.home-assistant.io/installation/linux#install-home-assistant-container) and [HTTP reverse-proxy documentation](https://www.home-assistant.io/integrations/http/#reverse-proxies).

## Validate and roll out

Render and inspect before rollout:

```sh
helm lint apps/home-assistant/chart
helm template home-assistant apps/home-assistant/chart --namespace home-assistant
```

The current workstation does not have Helm or kubectl installed. After the GitOps `main` change is pushed, use Argo CD to confirm sync and health, then run the live checks below through the available control-plane SSH access. Do not use a locally installed client as a prerequisite for this documented SSH path:

```sh
ssh -i ~/.ssh/id_rsa_control ubuntu@10.0.0.110 'sudo -n /usr/local/bin/k3s kubectl -n argocd get applications home-assistant'
ssh -i ~/.ssh/id_rsa_control ubuntu@10.0.0.110 'sudo -n /usr/local/bin/k3s kubectl -n home-assistant get deployment,pod,service,pvc,ingress'
```

Require the Application to report Synced and Healthy, the pod ready, and the PVC Bound. From an allowed home-LAN client, verify HTTPS and the UI at `https://home-assistant.atlas.lan`, certificate issuance, and denial outside the `10.0.0.0/8` allowlist. After initial setup, test persistence with a controlled pod restart and confirm configuration remains. Until these checks are performed, deployment and health remain unverified.

## Rollback and data safety

Revert the GitOps change on `main` and let Argo CD reconcile. If removing the Application or workload, preserve the PVC and backing NFS data: the claim has prune/delete protection, but the `truenas-nfs` StorageClass reclaim policy is `Delete`. Do not manually delete the PVC or NFS contents as part of routine rollback. Retain the data until recovery or deletion is explicitly approved, and verify a backup before relying on the configuration as the only copy.

## Limitations

NFS capacity, backup/restore, and filesystem behavior still require operator validation. Ordinary Kubernetes networking does not promise multicast/mDNS discovery, Bluetooth, or USB radio access. Those integrations need a separate design. No live deployment or LAN health check is claimed here.
