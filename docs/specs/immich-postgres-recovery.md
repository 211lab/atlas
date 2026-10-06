# Immich PostgreSQL recovery and local storage

## Goal

Run Immich against a new CloudNativePG database on `local-path`, with PostgreSQL
logical dumps protected by Restic on NFS, while preserving the failed initial
NFS-backed Cluster and its PVC until the replacement is proven healthy.

## Current evidence

- The initial `Cluster/immich-database` is `Cluster is unrecoverable and needs
  manual intervention`, `Initialized=True`, and `Ready=False`.
- Its `immich-database-1-initdb` Job exhausted retries. Logs show PostgreSQL
  `initdb` fails because the NFS data directory has wrong ownership (PostgreSQL
  runs as UID 26).
- The current `immich-database-1` PVC is bound to `truenas-nfs`; its PV reclaim
  policy is `Delete`.
- **ASSUMPTION:** The failed initial database contains no usable PostgreSQL
  database: every observed initdb attempt exited before initialization completed
  and removed its data directory. Preserve the old PVC/PV anyway until the new
  database is ready and cleanup is separately approved.

## User-visible behavior

Immich uses a newly named CloudNativePG Cluster with its PostgreSQL data on
`local-path`. A daily `pg_dump` is saved as a Restic snapshot on a separate
TrueNAS NFS PVC. The existing failed NFS-backed Cluster and PVC remain
untouched during rollout and are not used by Immich.

## Non-goals

- Do not delete, rename, patch, or change storage settings on the existing
  `Cluster/immich-database`, its failed initdb Job, its PVC, or its PV during
  this rollout.
- Do not change the Immich chart pin (`0.13.2`) or app image pin (`v3.2.0`).
- Do not delete the photo-library PVC or namespace.
- Do not claim backup readiness until a Restic snapshot is successfully
  created and can be listed.

## Acceptance criteria

- **Given** the failed NFS Cluster remains in place, **when** the local-path
  recovery resources are reconciled, **then** a distinct Cluster
  `immich-database-local` is created with the same PostgreSQL major version and
  required `vchord` extension, using `storageClass: local-path`.
- **Given** the new Cluster becomes ready, **when** the `Database` resource and
  Immich values reconcile, **then** both Immich and the backup CronJob consume
  the generated `immich-database-local-app` Secret.
- **Given** the initial NFS resources exist, **when** the recovery is deployed,
  **then** the original `immich-database` Cluster and its
  `immich-database-1` PVC/PV remain present and unmodified.
- **Given** the new database is ready, **when** Immich reconciles, **then** its
  Application is `Synced/Healthy`, the server and required components are
  Ready, and the ingress remains `immich.atlas.lan`.
- **Given** the backup PVC and sealed Restic credential are available, **when**
  a backup run succeeds, **then** Restic can list a snapshot tagged
  `immich-postgres` on the NFS-backed repository.
- **Given** this change is pushed, **when** both remotes are inspected, **then**
  GitHub and Gitea `main` point to the same commit.

## Constraints

- Use GitOps for desired state; do not hand-apply the application manifests.
- Preserve the corrected public OCI source path
  `ghcr.io/immich-app/immich-charts` + chart `immich` version `0.13.2`.
- Store only a SealedSecret for the Restic password; never commit a plaintext
  credential.
- Keep media and backup data on separate `truenas-nfs` PVCs; keep the new
  database on node-local `local-path`.
- The Restic job backs up PostgreSQL only, not the media library.

## Plan

1. Add a new CNPG Cluster and Database resource rather than resetting the
   initialized-but-unready NFS Cluster.
2. Add the 100Gi NFS backup PVC, daily Restic dump CronJob, and sealed password.
3. Point Immich and the backup job at the new Cluster's generated application
   Secret; update the runbook and application catalog.
4. Push identical Git history to both remotes and let Argo CD reconcile.
5. Verify the new PVC has `local-path`, CNPG reaches Ready, Immich reaches
   `Synced/Healthy`, and a Restic backup succeeds.

## Rollback and data handling

Before any application data is written to the new database, rollback means
stopping the new rollout while retaining both database PVCs for investigation.
After user data is written, rollback requires a Restic restore into a separate
healthy Cluster; do not switch Immich to the failed NFS Cluster.

The old NFS Cluster, failed Job, PVC, and PV are deliberately retained. Their
eventual cleanup is a separate destructive operation requiring a fresh check of
ownership/reclaim policy and explicit approval; this spec does not authorize
their deletion.

## Open questions

- Validate the TrueNAS capacity available for the 100Gi backup PVC before
  relying on it for production data.
- Rehearse a Restic restore and separately back up the media library before
  treating Immich as the only copy of photos.
