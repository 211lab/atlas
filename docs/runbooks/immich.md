# Immich operations

Immich runs from the official chart and CloudNativePG operator. Its single PostgreSQL 18 instance uses `local-path`, whose data is node-local; node loss requires restoration from the off-node dump. The library and backup PVCs use separate `truenas-nfs` subdirectories. Database dumps do not back up media: independently back up the library before relying on Immich as the only copy.

CloudNativePG creates `immich-database-app` for the database connection. `immich-secrets` is a strict-scope SealedSecret containing only the Restic repository encryption password. Back up the Sealed Secrets controller key according to [Sealing secrets](sealing-secrets.md); without it, the encrypted Restic snapshots cannot be read. The job runs daily at 02:00 UTC and retains 14 daily snapshots; confirm this policy and the 100Gi backup PVC capacity before production use.

## Restore database

Pause the Immich application. Mount `immich-backup` in a one-off Restic pod and use `RESTIC_PASSWORD` from `immich-secrets` to list snapshots and export one with `restic dump <snapshot> /dump/immich.sql > immich.sql`. Bootstrap a replacement CloudNativePG cluster with the same PostgreSQL major version and Immich extensions, then import the dump into the `app` database using the generated `immich-database-app` credentials. Resume Immich and verify sign-in, assets, and search. Rehearse node-loss recovery before storing irreplaceable photos.

## Rotate credentials

CloudNativePG manages database credentials; follow its role/secret rotation procedure rather than editing a password in Git. To rotate `RESTIC_PASSWORD`, initialize a new repository or re-key the existing Restic repository first; changing only the Kubernetes secret makes existing snapshots unreadable. Never commit a plaintext Secret. Seal as name `immich-secrets`, namespace `immich`, strict scope, and replace only the encrypted field in `apps/immich/manifests/restic-sealed-secret.yaml`.
