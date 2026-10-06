# Immich operations

The GitOps declaration pins the OCI chart repo
`ghcr.io/immich-app/immich-charts`, chart `immich` version `0.13.2` (Immich
`v3.2.0`), with CloudNativePG PostgreSQL 18 and the required `vchord` extension.
The recovery database is configured as a distinct Cluster,
`immich-database-local`, on node-local `local-path`. The media library and the
separate `immich-backup` PVC use `truenas-nfs`. Local database storage is not
node-loss protection; recovery depends on off-node logical dumps.

## Bootstrap failure and preservation

The original NFS-backed `Cluster/immich-database` was recorded as
`Initialized=True`, `Ready=False`, with its initdb Job exhausting retries after
PostgreSQL could not initialize the NFS data directory with UID 26 ownership.
Its `immich-database-1` PVC is bound to `truenas-nfs`, and its PV reclaim policy
is `Delete`.

**Do NOT delete the current initialized-but-unready cluster's PVC or PV to reset
it.** Do not delete, rename, patch, or change storage settings on the original
`immich-database` Cluster, its failed initdb Job, its PVC, or its PV during this
recovery. The old NFS resources are temporarily preserved for investigation and
are not used by Immich after cutover. Their cleanup is a separate destructive
operation requiring a fresh ownership/reclaim-policy check and explicit
approval.

Use a distinct Cluster named `immich-database-local` with
`storageClass: local-path`; do not try to change the existing Cluster's PVC
storage class or reuse its name. Reconcile recovery resources through GitOps.
The new cluster uses PostgreSQL 18 and a corresponding `Database` resource for
`vector`, `vchord`, `earthdistance`, and `cube`. Wait for the new Cluster to be
ready before relying on its generated `immich-database-local-app` Secret. Keep
the old NFS Cluster/PVC/PV in place until the replacement is proven healthy and
cleanup is separately approved.

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

A configured schedule is not proof of a successful backup. Backup readiness is
unverified until a backup Job succeeds and Restic can list its snapshot.

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
   PostgreSQL major version, with the Immich extensions installed. Do not
   restore into or switch Immich back to the failed original NFS Cluster. Use
   the replacement Cluster's generated `<cluster>-app` Secret to connect to its
   `app` database and import the plain SQL dump with `psql` and
   `ON_ERROR_STOP=1`.
5. Update Immich and the backup job to reference the replacement Cluster's
   generated application Secret through GitOps. Resume Immich only after the
   database restore and connection have been checked; verify application
   behavior separately. Retain both old and replacement PVCs until recovery is
   proven and cleanup is separately approved.

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
