# Immich clean reset after failed PostgreSQL bootstrap

## Goal

Deploy Immich from a clean namespace using a new CloudNativePG database on
`local-path`, with PostgreSQL logical dumps protected by Restic on NFS.

## Current evidence

- `Cluster/immich-database` is `Cluster is unrecoverable and needs manual
  intervention`, `Initialized=True`, and `Ready=False`.
- Its `immich-database-1-initdb` Job exhausted retries. Logs show PostgreSQL
  `initdb` fails because the NFS data directory has wrong ownership (PostgreSQL
  runs as UID 26).
- `immich-database-1` is bound to `truenas-nfs`; its PV reclaim policy is
  `Delete`. `immich-library` is a 50Gi NFS PVC, and Immich's server never became
  ready.
- CNPG 1.30.1 refuses to create a blank primary after this Cluster is marked
  initialized if its PVC group is removed. The replacement therefore uses a
  separate Cluster name and never attempts to reset this Cluster in place.

## User authorization

The user explicitly chose **Immich namespace, including library** for the reset.
This authorizes deleting all resources in namespace `immich`, including the
failed database PVC/PV and the NFS-backed photo-library PVC/PV. It does not
authorize deleting resources in other namespaces or the CloudNativePG operator
in `cnpg-system`.

## User-visible behavior

Argo CD recreates the `immich` namespace from the current GitOps declaration.
Immich uses the newly named CloudNativePG Cluster `immich-database-local` with
PostgreSQL data on `local-path`. The photo library and daily PostgreSQL Restic
backup use separate TrueNAS NFS PVCs.

## Non-goals

- Do not delete resources outside the `immich` namespace, including the CNPG
  operator, other applications, Argo CD, or Gitea.
- Do not change the Immich chart pin (`0.13.2`) or image pin (`v3.2.0`).
- Do not commit plaintext credentials.
- Do not claim backup readiness until a Restic snapshot is successfully
  created and can be listed.

## Acceptance criteria

- **Given** the failed NFS design is removed from the GitOps source, **when**
  the namespace reset is performed, **then** all pre-reset resources in
  `immich` are removed, including the legacy Cluster/Database, failed initdb
  Job/pods, database PVC/PV, and library PVC/PV; no other namespace is changed.
- **Given** the namespace is gone, **when** Argo CD reconciles the current
  source, **then** it recreates only the new design: one local-path Cluster
  `immich-database-local`, its Database, the library and backup PVCs, and the
  Immich chart resources.
- **Given** the new Cluster becomes ready, **when** Immich and the backup job
  reconcile, **then** both use `immich-database-local-app` and no reference to
  the failed `immich-database-app` remains in the desired manifests/values.
- **Given** the new database is ready, **when** Immich reconciles, **then** its
  Application is `Synced/Healthy`, required pods are Ready, and ingress remains
  `immich.atlas.lan`.
- **Given** the backup PVC and sealed Restic credential are available, **when**
  a backup run succeeds, **then** Restic can list a snapshot tagged
  `immich-postgres` on the NFS-backed repository.
- **Given** changes are pushed, **when** both remotes are inspected, **then**
  GitHub and Gitea `main` point to the same commit.

## Constraints

- Use GitOps for desired state; do not hand-apply application manifests.
- Preserve the corrected OCI source `ghcr.io/immich-app/immich-charts` + chart
  `immich` version `0.13.2`.
- Keep the new PostgreSQL volume on `local-path`; put media and backups on
  separate `truenas-nfs` PVCs.
- The Restic job backs up PostgreSQL only, not the media library.

## Plan

1. Remove the legacy NFS `Cluster` and `Database` manifests from the active
   Immich source; retain the local-path Cluster, local Database, and backups.
2. Temporarily disable automated sync on the Immich child Application through
   GitOps, push to both remotes, and verify the app-of-apps has applied that
   manual-sync policy.
3. Terminate the stale Argo sync operation pinned to the old revision and
   verify the child Application now targets the current Git revision.
4. Delete namespace `immich` as explicitly authorized; wait for it and all
   pre-reset PVC/PV backing volumes to be reclaimed.
5. Re-enable automated sync in GitOps and push to both remotes. Let Argo CD
   recreate the namespace and all resources from the fresh desired state; do
   not run `kubectl apply` for application resources.
6. Verify local-path database readiness, Immich health, new PVC identities, and
   one successful Restic snapshot.

## Destructive impact and rollback

Deleting namespace `immich` removes the existing 50Gi library PVC and its bound
NFS PV (reclaim policy `Delete`), so any contents in that volume will be lost.
It also removes the failed database PVC/PV and generated secrets/jobs. The user
has explicitly authorized this Immich-namespace reset. The previous library and
database contents cannot be recovered from these volumes afterward; the new
database and library are recreated empty.

Before namespace deletion, the GitOps change can be reverted. After deletion,
rollback cannot restore the old NFS media or database contents. Recovery would
require independent photo backups and/or Restic snapshots from the new design.

## Open questions

- Validate TrueNAS capacity for the 100Gi backup PVC before relying on it for
  production.
- Rehearse a Restic restore and separately back up the media library before
  treating Immich as the only copy of photos.
