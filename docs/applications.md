# Atlas applications

Everything deployed to the cluster through Argo CD, and how each app is
structured. Platform components (Gitea, Argo CD, cert-manager, sealed-secrets,
monitoring) are covered in [GitOps platform](gitops-platform.md); this is the
application catalog.

Two app styles are in use:

- **third-party stack** — an upstream Helm chart pinned in `gitops/apps/<name>.yaml`
  with values in `helm/values/<name>.yaml` (via the `$values` ref);
- **in-house app** — an in-repo chart at `apps/<app>/chart/` with its own
  `values.yaml`, referenced by `gitops/apps/<app>.yaml`.

CI lives in each app's own repository (`.gitea/workflows/build.yaml`): on a `v*`
tag it builds/pushes an image to `registry.atlas.lan/atlas-admin/<app>` and, in
the same job, commits the new tag into this repo's chart values. Gitea webhooks
Argo CD; there is no registry poller. Onboarding is automated by
[`atlas-deploy-app`](../.opencode/skills/atlas-deploy-app/SKILL.md).

| App | Style | Chart / values | Argo Application | Namespace | Ingress |
| --- | --- | --- | --- | --- | --- |
| demo-app | in-repo | `examples/demo-app/chart` | `gitops/apps/demo-app.yaml` | `demo` | `demo.atlas.lan` |
| redop | in-repo | `apps/redop/chart` | `gitops/apps/redop.yaml` | `redop` | `redop.atlas.lan` |
| immich | third-party + operator | `ghcr.io/immich-app/immich-charts/immich` `0.13.2` + `helm/values/immich.yaml` | `gitops/apps/immich.yaml` (pending) | `immich` | `immich.atlas.lan` (pending) |

## demo-app — reference implementation

The canonical worked example and the smallest GitOps app.

- **Chart:** `examples/demo-app/chart` (nginx static page, Deployment + Service +
  Ingress).
- **Image:** `registry.atlas.lan/atlas-admin/demo-app:<tag>`.
- **CI:** `examples/demo-app/.gitea/workflows/build.yaml` — builds with the
  runner's dind (`docker:25-git`), writes `~/.docker/config.json` directly, and
  promotes semver tags into `examples/demo-app/chart/values.yaml`.
- **Secrets:** `gitops/sealed/demo-gitea-registry.yaml` (image pull).
- **Argo:** `gitops/apps/demo-app.yaml`, path `examples/demo-app/chart`.

## redop — RED Operations Platform

In-house app hosting OpenExecutive (FastAPI API + Next.js UI) with a bundled
PostgreSQL, defined entirely in one chart.

- **Chart:** `apps/redop/chart` (API + UI Deployments/Services, Ingress,
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
- **Known:** `redop-api` liveness probe intermittently times out.

## immich — photo/video library

Third-party app using the maintained upstream chart plus a CloudNativePG-managed
PostgreSQL, because Immich v3 requires the `vchord` extension.

- **Operator:** `gitops/apps/cnpg.yaml` + `helm/values/cnpg.yaml`
  (CloudNativePG `0.29.1` / operator v1.30.1, namespace `cnpg-system`,
  sync-wave `-1`).
- **Chart:** `ghcr.io/immich-app/immich-charts/immich` `0.13.2` (Immich v3.2.0)
  with pinned values `helm/values/immich.yaml` and the `$values` ref.
- **Data:** `apps/immich/manifests/` — 50Gi `truenas-nfs` ReadWriteMany library
  PVC, the `immich-database` CNPG `Cluster` (PostgreSQL 18 on `local-path` +
  `vchord-scratch`), and the `Database` CR installing
  `vector`/`vchord`/`earthdistance`/`cube`.
  DB credentials come from the operator-generated `immich-database-app` Secret.
- **Backups:** daily PostgreSQL dumps to Restic snapshots on a separate 100Gi
  `truenas-nfs` PVC; keep 14 daily snapshots. The Restic key is sealed.
- **Namespace:** `immich`; **Ingress:** `immich.atlas.lan` (TLS `atlas-ca`);
  valkey (Redis) and a 10Gi ML-model cache PVC run in-chart.
- **Merged locally from upstream, not yet pushed to the forge** — reconcile after
  the branch is pushed; validate backup capacity and practice recovery first.

## Adding an app

Follow `CONTRIBUTING.md` and the `atlas-deploy-app` skill. In short: create the
chart + `gitops/apps/<app>.yaml`, add any namespace registry pull secret as a
SealedSecret, push to the forge, then tag a release so CI builds and promotes.
Argo CD does the rest.
