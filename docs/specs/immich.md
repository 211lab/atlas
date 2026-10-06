# Immich self-hosting specification

## Goal

Deploy Immich as a self-hosted photo and video library—an alternative to Google Photos—on the Atlas K3s cluster, managed through the repository's Argo CD GitOps flow.

## User-visible behavior

- People on the Atlas home LAN can open `https://immich.atlas.lan` and use Immich's web interface and mobile apps.
- Immich stores uploaded media persistently on TrueNAS NFS and PostgreSQL on cluster-local persistent storage.
- A scheduled database dump is saved as an incremental/deduplicated snapshot history in a dedicated directory/PVC on the existing TrueNAS NFS export, with documented restore steps.
- The deployment is reconciled from Git by Argo CD and uses the existing Atlas internal CA/TLS and DNS conventions.

## Non-goals

- Public internet exposure, remote access, or identity-provider/SSO integration.
- Migrating or importing an existing photo collection, Google Takeout, or configuring clients/backups.
- Provisioning a new VM or changing cluster/storage infrastructure.
- GPU/accelerator enablement or custom ML tuning.

## Acceptance criteria

1. **GitOps-managed deployment** — Given the root app-of-apps is reconciling, when this change is merged, then an Immich Argo CD Application deploys Immich into its own namespace with automated sync and self-heal.
2. **LAN-only ingress** — Given a client on the allowed private LAN, when it visits `https://immich.atlas.lan`, then Traefik routes to Immich with a certificate from the Atlas CA; clients outside the configured LAN range are denied.
3. **Persistent media** — Given Immich pods are restarted or rescheduled, when they return healthy, then uploaded media remains available from persistent storage.
4. **Local PostgreSQL storage** — Given PostgreSQL restarts or its pod is rescheduled, when the database returns, then it uses a persistent volume on the cluster's local-path storage and Immich can reconnect. PostgreSQL data is not placed on NFS.
5. **Network backups** — Given a scheduled backup runs, when it completes, then a restorable PostgreSQL logical dump is stored in an incremental/deduplicated snapshot history on the dedicated network backup share, with retention and recovery steps documented. Backups must not depend on the PostgreSQL pod's local volume surviving.
6. **No plaintext credentials** — Given repository configuration is reviewed, then no database password or other credential is committed in plaintext; secrets follow the repository's Sealed Secrets conventions.
7. **Render validation** — Given the selected chart and values, when Helm rendering and YAML validation run, then manifests render successfully and include the expected ingress and persistent volume claims.

## Constraints

- Use the established `gitops/apps/` Argo CD app-of-apps pattern and repository-managed Helm configuration.
- Use Atlas internal TLS (`atlas-ca`) and LAN-only ingress conventions.
- Use the existing cluster-local `local-path` StorageClass for PostgreSQL data; use TrueNAS NFS for media and a dedicated NFS backup location for database dumps.
- Avoid committing plaintext credentials.

## Assumptions

- ASSUMPTION: The selected scope is an in-cluster K3s deployment using the merged CloudNativePG operator and Immich OCI chart, rather than a separate VM or hand-managed PostgreSQL StatefulSet.
- ASSUMPTION: LAN-only means the repository's existing `10.0.0.0/8` Traefik allowlist policy; this is the same policy used by current internal apps.
- ASSUMPTION: Immich's web, API, machine-learning, database, and cache components can run on the current cluster; final resource sizing remains subject to available capacity.
- ASSUMPTION: User directed PostgreSQL to cluster-local storage and incremental/differential dump backups to a dedicated network share. The single CloudNativePG instance uses Atlas `local-path`, which is node-local; node loss requires restoration from the off-node logical dump.
- ASSUMPTION: “Incremental/differential backups” means a complete logical PostgreSQL dump at each scheduled run, retained through Restic's content-deduplicated snapshots on an NFS-backed repository. `pg_dump` itself is not incremental. User chose a dedicated subdirectory/PVC on the existing `/mnt/data/atlas-k8s` export, separate from the media PVC.
- ASSUMPTION: Initial backup policy is daily at 02:00, retain 14 daily snapshots; this is a safe starting point, not a user-specified RPO/retention policy, and must be confirmed before production.
- ASSUMPTION: `immich.atlas.lan` is resolvable through the existing wildcard DNS, as with other `*.atlas.lan` services.
- ASSUMPTION: User has not specified library size, exact backup retention/RPO, or hardware acceleration. Database and Restic credentials are randomly generated and stored only as a strict-scope SealedSecret. The daily 02:00 / 14-snapshot policy and PVC capacity settings are conservative initial defaults and need confirmation before production use.

## Plan

1. Add this specification before implementation.
2. Use official Immich OCI chart `oci://ghcr.io/immich-app/immich-charts/immich` pinned to `0.13.2` (app `v3.2.0`) with the CloudNativePG operator and VectorChord extension configuration.
3. Keep the PostgreSQL Cluster on `local-path`, media on `truenas-nfs`, and add a scheduled logical-dump-to-Restic snapshot backup on a separate NFS-backed PVC. Keep credentials sealed.
4. Validate rendered manifests, YAML, storage/ingress/secret requirements, and backup job behavior. Do not claim runtime health without cluster access and post-sync checks.

## Rollback

Disabling/removing the Immich Argo CD Application preserves the CloudNativePG Cluster and persistent library/backup PVCs via Argo prune/delete protections. This deliberately leaves the database cluster running; scale or hibernate it separately if desired. Do not delete the Cluster or PVCs until the operator confirms the data may be discarded and a restore has been tested.

## Open questions / rollout checks

- Verify the generated SealedSecret is accepted/unsealed by the live controller after Argo sync; rendering cannot prove live decryption.
- Confirm available cluster resources and desired media-library capacity.
- The user selected a separate PVC/subdirectory on the existing TrueNAS export for backup data; confirm NAS capacity and retention before production use.
- Database backups do not include Immich media assets; separately back up the library before treating Immich as the only copy of photos.
- Runtime acceptance (login, upload, playback, mobile client, restart recovery) requires a post-sync smoke test on the LAN.
- Helm, kubectl, and kubeseal are available under `~/.local/bin`; Atlas kubeconfig is available at `~/.kube/atlas-admin.yaml`.
