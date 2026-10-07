# Atlas applications

Application declarations and how each app is structured. For dated live
coverage of **every** namespace, workload, image tag, placement, ingress, claim
and Argo state, see the [2026-10-07 infrastructure review](infrastructure-review.md)
and [focused dependency diagrams](architecture/application-dependencies.md).
Platform components (Gitea, Argo CD, cert-manager, sealed-secrets,
monitoring) are covered in [GitOps platform](gitops-platform.md); this is the
application catalog. For what is planned but not yet deployed, see the
[software install backlog](backlog.md).

Two app styles are in use:

- **third-party stack** — an upstream Helm chart pinned in `gitops/apps/<name>.yaml`
  with values in `helm/values/<name>.yaml` (via the `$values` ref);
- **in-house app** — an in-repo chart at `apps/<app>/chart/` with its own
  `values.yaml`, referenced by `gitops/apps/<app>.yaml`.

CI lives in each app's own repository (`.gitea/workflows/build.yaml`): on a `v*`
tag it builds/pushes an image to `registry.atlas.lan/atlas-admin/<app>` and, in
the same job, commits the new tag into this repo's chart values. Gitea webhooks
Argo CD; there is no registry poller. Onboarding is automated by
the repository skill `.opencode/skills/atlas-deploy-app/SKILL.md`.

| App | Style | Chart / values | Argo Application | Namespace | Ingress |
| --- | --- | --- | --- | --- | --- |
| redop | in-repo | `apps/redop/chart` | `gitops/apps/redop.yaml` | `redop` | `redop.atlas.lan` |
| immich | third-party + operator | OCI repo `ghcr.io/immich-app/immich-charts`, chart `immich` `0.13.2` + `helm/values/immich.yaml` | `gitops/apps/immich.yaml` | `immich` | `immich.atlas.lan` |
| 3f-app | in-repo | `apps/3f-app/chart` | `gitops/apps/3f-app.yaml` | `3f-app` | `3fapp.atlas.lan` |
| dave-study | in-repo | `apps/dave-study/chart` | `gitops/apps/dave-study.yaml` | `dave-study` | `dave-study.atlas.lan` |
| home-assistant | in-repo | `apps/home-assistant/chart` | `gitops/apps/home-assistant.yaml` | `home-assistant` | `home-assistant.atlas.lan` |
| docs (declared only) | in-repo | `apps/docs/chart` | `gitops/apps/docs.yaml` | `docs` (not live) | `docs.atlas.lan` (DNS only; no live ingress) |

## redop — RED Operations Platform

In-house app hosting OpenExecutive (FastAPI API + Next.js UI) with a bundled
PostgreSQL, defined entirely in one chart.

- **Chart:** `apps/redop/chart` (API, UI, cockpit and worker Deployments,
  migration Job, Services, Ingress,
  Traefik `Middleware` `redop-ipallow`, and a `postgres:16.4-alpine` Deployment
  with its own PVC).
- **Namespace:** `redop`; **Ingress:** `redop.atlas.lan` (TLS `atlas-ca`,
  restricted to `10.0.0.0/8` by the ipallow middleware).
- **Storage:** `redop-data` (10Gi) and `redop-postgres-data` (10Gi) on
  `truenas-nfs`, ReadWriteOnce.
- **Images:** `registry.atlas.lan/atlas-admin/redop-api|redop-ui:<tag>`.
- **Secrets:** `gitops/sealed/redop-postgres.yaml` (DB password / `DATABASE_URL`),
  `redop-secrets.yaml` (app secrets), `redop-registry.yaml` (image pull).
- **Config:** `execEmail`, `defaultModel` (`openrouter/auto`), resource requests
  and ports in `apps/redop/chart/values.yaml`.
- **Observed 2026-10-07 (review K/D):** all five Deployments Ready and migration
  Job succeeded; live app tags `sha-acbcee9`, checkout `sha-de44d86`. An older
  API pod retained a probe-failure event; current API has zero restarts. Ingress
  routes `/red` to API, `/screens` to UI, root and `/api/backend` to cockpit.
  Argo Synced refers to forge main, not this checkout. Cockpit authentication is
  declared disabled; IP restriction is not an identity layer.

## immich — photo/video library

Third-party app using the maintained upstream chart plus a CloudNativePG-managed
PostgreSQL, because Immich v3 requires the `vchord` extension.

- **Operator:** `gitops/apps/cnpg.yaml` + `helm/values/cnpg.yaml`
  (CloudNativePG `0.29.1` / operator v1.30.1, namespace `cnpg-system`,
  sync-wave `-1`).
- **Chart:** OCI repo `ghcr.io/immich-app/immich-charts`, chart `immich`
  `0.13.2` (Immich v3.2.0), with pinned values `helm/values/immich.yaml` and
  the `$values` ref.
- **Data:** `apps/immich/manifests/` — `immich-database-local` CNPG `Cluster`
  (PostgreSQL 18 on `local-path` + `vchord-scratch`) and a `Database` CR
  installing `vector`/`vchord`/`earthdistance`/`cube`. Immich and the backup job
  consume its generated `immich-database-local-app` Secret. The photo library
  uses a separate 50Gi `truenas-nfs` ReadWriteMany PVC.
- **Backups:** the job is configured to create daily PostgreSQL logical dumps as
  Restic snapshots on a separate 100Gi `truenas-nfs` PVC, with 14 daily
  snapshots retained. The Restic password is sealed. The first one-off backup
  Job succeeded and Restic listed snapshot `86133bb9` at `2026-10-07 00:03:32
  UTC` (49.796 MiB, tag `immich-postgres`); the Job was deleted afterward. This
  verifies one snapshot only, not scheduled or long-term backup health. The
  PostgreSQL dump does not back up the media library; arrange an independent
  library backup.
- **Observed 2026-10-07 (review K):** the scheduled 02:00 UTC Job also succeeded,
  lastSuccessfulTime `02:00:12Z`. Snapshot contents/retention and restores were
  not checked by the read-only review. One ready PostgreSQL primary and its
  local-path PV are on cp1; node loss requires recovery, not automatic DB HA.
- **Namespace:** `immich`; **Ingress:** `immich.atlas.lan` (TLS `atlas-ca`);
  valkey (Redis) and a 10Gi ML-model cache PVC run in-chart. The database dump
  does not back up the media library.

## Adding an app

Follow `CONTRIBUTING.md` and the `atlas-deploy-app` skill. In short: create the
chart + `gitops/apps/<app>.yaml`, add any namespace registry pull secret as a
SealedSecret, push to the forge, then tag a release so CI builds and promotes.
Argo CD does the rest.
