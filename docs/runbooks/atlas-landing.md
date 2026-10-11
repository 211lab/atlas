# Atlas landing page runbook

`atlas.lan` (and `www.atlas.lan`) is the Atlas home page: an instance of
[Homepage](https://gethomepage.dev) that also acts as a self-updating directory
of cluster services. Its background is regenerated from the local weather.

Chart: `apps/atlas-landing/chart` · Argo Application: `gitops/apps/atlas-landing.yaml`
Namespace: `atlas-landing`

## What runs

The Deployment has three parts plus an init container:

| Part | Image | Purpose |
| --- | --- | --- |
| `seed` (init) | `registry.atlas.lan/atlas-admin/atlas-landing` | On first start, copies the original artwork and favicons onto the shared volume if no background exists. |
| `homepage` | `ghcr.io/gethomepage/homepage` (pinned) | The dashboard. Config is mounted from the `atlas-landing-config` ConfigMap. |
| `background` | `nginx:1.27-alpine` | Serves the current background from the shared PVC at `/weather/`. |

Shared volume: PVC `atlas-landing-background` (`truenas-nfs`, ReadWriteMany),
holding `background.jpg`, `weather.json` and the favicons.

Ingress (Traefik, `atlas-ca` TLS, `10.0.0.0/8` ipallow): `/weather` → background
nginx, `/` → Homepage.

## Service discovery

Homepage lists services from Ingress annotations — no manual list. Opt a route in
by adding:

```yaml
gethomepage.dev/enabled: "true"
gethomepage.dev/name: Display Name
gethomepage.dev/group: Platform   # infra tier: Platform | Services | Apps
gethomepage.dev/description: Short description
gethomepage.dev/icon: immich.png  # optional, from selfh.st/dashboard-icons
```

The homepage ServiceAccount (`atlas-landing-homepage`) has a cluster-wide but
read-only ClusterRole limited to `ingresses` plus `pods`/`nodes`/`namespaces`.
Add annotations to a route and it appears after Homepage reconciles (no restart
needed). Groups render in the order set in `settings.yaml`.

## Weather background

A CronJob `atlas-landing-weather` runs every 3 hours (America/New_York). It:

1. fetches current conditions for Swarthmore, PA (19081) from Open-Meteo;
2. asks OpenRouter `google/gemini-2.5-flash-image` for a photorealistic scene in
   which the word "Atlas" appears as graffiti matching the weather;
3. asks OpenRouter `google/gemini-2.5-flash` to verify the image (spelling,
   photorealism, weather match);
4. publishes the image and `weather.json` **only if verification passes**.

A failed or rejected run leaves the current background untouched, so the last
good image (initially the original artwork) keeps serving. The OpenRouter API key
is the SealedSecret `atlas-landing-secrets` (`OPENROUTER_API_KEY`).

Knobs in `apps/atlas-landing/chart/values.yaml` under `weather:` — schedule,
coordinates/place, models. To disable generation set `weather.enabled: false`.

## Operate

```sh
export KUBECONFIG=~/.kube/atlas-admin.yaml

# Argo state
kubectl -n argocd get application atlas-landing \
  -o custom-columns=SYNC:.status.sync.status,HEALTH:.status.health.status

# Workloads
kubectl -n atlas-landing get deploy,po,cronjob,ingress,certificate

# Trigger a generation now
kubectl -n atlas-landing create job --from=cronjob/atlas-landing-weather weather-manual
kubectl -n atlas-landing logs job/weather-manual -f

# Inspect the last accepted image metadata
kubectl -n atlas-landing exec deploy/atlas-landing -c background -- cat /data/weather.json
```

## Change the code

The generator image is built by the landing repo's CI
(`atlas-landing/.gitea/workflows/build.yaml`). Tag a release to ship it; CI
promotes `image.tag` in `apps/atlas-landing/chart/values.yaml` and Argo redeploys:

```sh
cd ~/atlas-landing
git tag v0.3.0 && git push atlas v0.3.0
```

Homepage and nginx are pinned upstream images in `values.yaml`; bump the tags
there and push the platform repo.

## Rollback

- Restore the previous generator tag by reverting the CI promotion commit.
- To serve the original artwork again, delete `/data/background.jpg` on the PVC
  and restart the Deployment (the seed init re-copies it); or set
  `weather.enabled: false` to stop regeneration.
- Full removal: delete `gitops/apps/atlas-landing.yaml` and `apps/atlas-landing/`;
  Argo prunes the Application and its resources. The PVC is deleted with it.
