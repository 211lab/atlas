# Immich operations

The GitOps declaration pins the OCI chart repo
`ghcr.io/immich-app/immich-charts`, chart `immich` version `0.13.2` (Immich
`v3.2.0`), with CloudNativePG PostgreSQL 18 and the required `vchord` extension.
The recovery database is configured as a distinct Cluster,
`immich-database-local`, on node-local `local-path`. The media library and the
separate `immich-backup` PVC use `truenas-nfs`. Local database storage is not
node-loss protection; recovery depends on off-node logical dumps.

## Bootstrap failure and database design

The original NFS-backed `Cluster/immich-database` was recorded as
`Initialized=True`, `Ready=False`, with its initdb Job exhausting retries after
PostgreSQL `initdb` failed because the NFS data directory had incorrect
ownership for PostgreSQL's UID 26. CNPG 1.30.1 treats that Cluster as already
initialized and will not create a blank primary if its PVC group is removed, so
it cannot be reset in place. The replacement is a distinct
`immich-database-local` Cluster on `local-path`, with its own PostgreSQL 18 data
volume and `Database` resource for `vector`, `vchord`, `earthdistance`, and
`cube`. Immich and the backup job use its generated
`immich-database-local-app` Secret. Reconcile the design through GitOps and wait
for the new Cluster to be ready before relying on that Secret.

## Approved namespace reset (completed)

The user explicitly approved a one-time reset of namespace `immich` for this
rollout, including its library data. After the failed NFS Cluster and Database
are removed from the active GitOps source, temporarily disable automated sync on
the Immich child Application through GitOps and wait for the root app to apply
that policy. Terminate the stale sync operation pinned to the old revision and
verify the application targets the current Git revision. Then delete the entire
`immich` namespace and allow Argo CD to recreate it from Git after automated
sync is re-enabled.

This removes every resource in the namespace, including the failed database
Cluster/Database, initdb Job and pods, secrets, and all PVCs/PVs, including the
50Gi library PVC/PV. The library PV's `Delete` reclaim policy means its contents
will be lost. Do not affect any other namespace or the CloudNativePG operator
in `cnpg-system`; do not hand-apply application resources.

This approval is for that one-time rollout reset, not standing authorization
for future resets. For every repeat reset, stop before deletion and obtain fresh,
explicit user confirmation that names namespace `immich` and acknowledges that
all its resources and library/database data will be deleted. Before proceeding,
verify that the active GitOps source contains only the intended
`immich-database-local` design, that the deletion target is exactly `immich`,
and that no other namespace or the operator is in scope. Without that
confirmation and those checks, do not delete the namespace or any library
PVC/PV. Once confirmed, delete only namespace `immich`, wait for its resources
and bound volumes to be reclaimed, then let Argo CD recreate the desired
resources from Git.

## Completed rollout verification (2026-10-07)

The explicitly approved `immich` namespace wipe is complete. The old Immich PVs
are gone, and fresh library, database, backup, and ML-model PVCs are Bound.
`immich-database-local` is healthy and primary, with its 10Gi PVC on
`local-path`. The server, machine-learning, and valkey Deployments are all 1/1
Ready; `immich-tls` is Ready. Argo CD root and Immich are `Synced/Healthy`, and
both `https://immich.atlas.lan/` and `/api/server/ping` returned HTTP 200.

At initial rollout validation, GitHub and Gitea `main` both pointed to
`151202e`. A one-off backup Job succeeded; Restic listed snapshot `86133bb9` at
`2026-10-07 00:03:32 UTC` (49.796 MiB, tagged `immich-postgres`). The Job was
deleted afterward. This confirms one snapshot only; a restore rehearsal,
long-term backup health, and NAS capacity validation have not been established.

## Normal backups

The `immich-postgres-backup` CronJob is configured for 02:00 UTC daily. It runs
`pg_dump --no-owner` for the database named in the CNPG-generated application
Secret, writes `/dump/immich.sql` to temporary `emptyDir` storage, and sends the
dump to Restic. Restic uses repository `/backup/restic` on the separate 100Gi
`immich-backup` NFS PVC, tags snapshots `immich-postgres`, and keeps 14 daily
snapshots. This backs up PostgreSQL only, not the media library; arrange an
independent backup for the library.

Check the CronJob and its latest Job, then inspect the Job's `dump` and `restic`
container logs for errors. Before relying on a backup, use an authorized
temporary Restic pod with `immich-backup` mounted at `/backup` and
`RESTIC_PASSWORD` supplied from `immich-secrets` to run:

```sh
export RESTIC_REPOSITORY=/backup/restic
restic snapshots --tag immich-postgres
```

The successful one-off run verifies one snapshot only; scheduled and long-term
backup health and restore behavior remain unverified. PostgreSQL backups do not
protect the media library, which needs an independent backup.

## Restore PostgreSQL

1. Pause Immich through GitOps so it does not write during recovery.
2. In an authorized temporary Restic pod, mount `immich-backup` at `/backup`,
   supply `RESTIC_PASSWORD` from `immich-secrets`, and list candidate snapshots:
   `restic snapshots --tag immich-postgres`.
3. Export the chosen snapshot's logical dump, replacing `<snapshot-id>` with the
   selected snapshot ID:

   ```sh
   export RESTIC_REPOSITORY=/backup/restic
   restic dump <snapshot-id> /dump/immich.sql > immich.sql
   ```

4. Restore into a separate healthy CloudNativePG Cluster running the same
   PostgreSQL major version, with the Immich extensions installed. The intended
   target is the healthy `immich-database-local` Cluster; the failed NFS Cluster
   cannot be reset in place and is removed by the approved namespace reset. Use
   the target Cluster's generated `<cluster>-app` Secret to connect to its `app`
   database and import the plain SQL dump with `psql` and `ON_ERROR_STOP=1`.
5. Update Immich and the backup job to reference the replacement Cluster's
   generated application Secret through GitOps. Resume Immich only after the
   database restore and connection have been checked; verify application
   behavior separately. Retain the replacement PVC until recovery is proven.

Rehearse this procedure before depending on it for node-loss recovery. Database
restores do not restore the photo/video library.

## Credentials

CloudNativePG generates `<cluster>-app` with keys `host`, `user`, `password`,
and `dbname`; for the recovery Cluster this is `immich-database-local-app`.
Immich and the dump job consume those keys. CloudNativePG owns database
credentials: follow its role/secret rotation procedure rather than editing its
generated Secret or committing a database password.

`immich-secrets` is a strict-scope SealedSecret containing only the Restic
repository encryption password under `RESTIC_PASSWORD`. The CronJob consumes
the decrypted Secret key. Authorized operators can read the namespaced Secret
when needed, but must not put its value in logs, shell history, or Git. Back up
the Sealed Secrets controller key using [Sealing secrets](../sealing-secrets.md);
without that key the committed sealed value cannot be unsealed after controller
loss.

To rotate the Restic password, re-key the existing repository or initialize a
new repository before changing the Kubernetes Secret. Changing only
`RESTIC_PASSWORD` makes existing snapshots unreadable. Seal the replacement
value as `immich-secrets` in namespace `immich`, strict scope, and commit only
the encrypted value in `apps/immich/manifests/restic-sealed-secret.yaml`.
