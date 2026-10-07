# Nextcloud file sync and collaboration

Status: draft
Owner: —
Date: 2026-10-07

## Goal

Deploy Nextcloud on Atlas at `https://cloud.atlas.lan`, backed by CloudNativePG
PostgreSQL, Redis, and `truenas-nfs` data storage, so users can sync and share
files from the home LAN with data that survives restarts.

## User-visible behavior

- A LAN user opens `https://cloud.atlas.lan`, completes first-run admin setup, and
  uploads, syncs, and shares files.
- Files, accounts, shares, and metadata survive pod restarts and rescheduling.
- Background jobs (cron) run reliably.
- Argo CD reconciles the deployment; access uses `atlas-ca` TLS and the LAN
  allowlist.

## Non-goals

- Public internet exposure or federation with external Nextcloud instances.
- Nextcloud Office/Collabora or other apps beyond the base install.
- External/object storage configuration (S3 primary storage) in this scope.
- Migrating an existing Nextcloud instance.

## Acceptance criteria

- Given the root app-of-apps is reconciling and the CNPG operator is installed,
  when this change is merged, then an Argo CD Application deploys Nextcloud (and
  its Redis) plus a CNPG `Cluster` in the `nextcloud` namespace with automated
  sync and self-heal.
- Given a LAN client, when it visits `https://cloud.atlas.lan`, then Traefik
  routes to Nextcloud over `atlas-ca` TLS with the `10.0.0.0/8` allowlist; clients
  outside the range are denied.
- Given the Nextcloud pod is restarted or rescheduled, when it becomes ready, then
  files and metadata remain available (data on the NFS PVC; database on CNPG).
- Given the trusted proxy configuration, then Nextcloud recognizes Traefik as a
  trusted proxy so generated URLs and client IPs are correct.
- Given the pod template, then the database, Redis, and admin credentials come
  from SealedSecrets or the CNPG-generated Secret; none are plaintext in git.
- Given the chart and values, when Helm rendering runs, then it renders
  successfully and includes the Deployment, Service, Ingress, PVC, and TLS
  reference.
- Given the backup design, when it is rehearsed, then database dumps and data
  recovery restore a working instance.

## Constraints

- Use the upstream community Helm chart (`nextcloud/nextcloud`) pinned by version,
  with values in `helm/values/nextcloud.yaml` and the `$values` multi-source ref.
- Database via CNPG (`Cluster` + `Database` CRs in `apps/nextcloud/manifests`);
  Redis runs in-chart or as a small Deployment.
- User data on `truenas-nfs` `ReadWriteMany` (single writer is expected; RWX is
  for pod rescheduling flexibility).
- `atlas-ca` TLS and the Traefik `10.0.0.0/8` ipallow middleware.
- All secrets are SealedSecrets; use the CNPG-generated database app Secret where
  possible.

## Assumptions

- ASSUMPTION: The NFS export presents consistent POSIX locking; Nextcloud's
  file-locking is configured (Redis locking preferred) and the `.ocdata` marker is
  present, per Nextcloud's NFS guidance.
- ASSUMPTION: `overwritehost`/`overwriteprotocol` and `trusted_proxies` are set
  for the Traefik-fronted, reschedulable pod network.
- ASSUMPTION: Data and config directories persist across restarts; the default
  `/var/www/html` app code is treated as replaceable.
- ASSUMPTION: A single Nextcloud instance behind the upstream PHP-FPM/Apache image
  is sufficient; no horizontal scaling.
- ASSUMPTION: `cloud.atlas.lan` resolves via Pi-hole/hosts until ADR 0001 DNS is live.

## Plan

1. Add `apps/nextcloud/manifests/` — CNPG `Cluster` and `Database` CR for
   Nextcloud. Verify: cluster `Ready`; app Secret generated.
2. Add `gitops/apps/nextcloud.yaml` — upstream chart with `helm/values/nextcloud.yaml`
   (external database pointing at the CNPG Secret, Redis, NFS data PVC, ingress
   for `cloud.atlas.lan` with `atlas-ca` and the LAN middleware, trusted-proxy
   config, cron). Verify: `helm template nextcloud nextcloud/nextcloud --version
   <ver> -n nextcloud -f helm/values/nextcloud.yaml`.
3. Seal admin credentials and any app secrets.
4. **Backup design (required for this spec).** Define scheduled CNPG database
   dumps and a data/config backup to a separate target, with retention, plus a
   rehearsed restore. Verify: restore rehearsal recorded in the runbook.
5. Add `docs/nextcloud.md` runbook; update `docs/applications.md`.

## Tasks

- [ ] Add CNPG manifests and validate.
- [ ] Add chart values and render-validate.
- [ ] Seal admin credentials.
- [ ] Add the Argo CD Application.
- [ ] Define and rehearse backup/restore.
- [ ] Add runbook and update the applications catalog.
- [ ] Verify acceptance criteria (LAN HTTPS, persistence, cron, trusted proxy).

## Rollback

Delete `gitops/apps/nextcloud.yaml` and push; Argo CD prunes the chart resources.
Preserve the CNPG cluster, the NFS data/config PVCs, and their backups until data
removal is explicitly approved. Re-apply the prior revision to restore without
data loss.

## Open questions / rollout checks

- Confirm NFS locking behavior and whether Redis-based file locking is enabled.
- Data PVC size and expected growth.
- Whether mail/app notifications are needed (SMTP is out of scope here).
