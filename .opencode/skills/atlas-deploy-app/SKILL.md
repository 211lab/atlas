---
name: atlas-deploy-app
description: Use when deploying an application to the Atlas Kubernetes cluster with the Gitea forge and Argo CD GitOps. Handles onboarding an existing checkout by adding an "atlas" git remote, creating the Gitea repo and CI secrets, adding a build workflow, committing the Helm chart and Argo CD Application, pushing, tagging a release, and verifying the build-and-deploy. Triggers on "deploy to atlas", "deploy this app to the cluster", "git remote add atlas", "onboard an app", "push build tag deploy", "make this app deploy on our k3s cluster".
---

# Deploy an application to Atlas

Atlas is a k3s cluster with a self-hosted Gitea forge, a Gitea Actions runner
(CI), a built-in OCI registry, and Argo CD (GitOps). The delivery contract is:

```
git push / tag v* ─▶ Gitea repo ─▶ Actions runner builds+pushes image
                                        │
                                        └─ commits the new tag into the
                                           GitOps repo (211lab/atlas)
                                                │
                                      Gitea webhook ─▶ Argo CD syncs
```

There is **no registry poller**. The build job itself promotes the tag into the
platform repo, and Gitea notifies Argo CD.

The canonical worked example is the demo app; always read it before inventing
anything:

- `examples/demo-app/.gitea/workflows/build.yaml` (CI + promotion)
- `examples/demo-app/chart/` (Helm chart)
- `gitops/apps/demo-app.yaml` (Argo CD Application)

Full background: `docs/gitops-platform.md` and `docs/c4-architecture.md`.

## Preflight

Run these first and stop if any fail.

```sh
export KUBECONFIG=~/.kube/atlas-admin.yaml
kubectl version >/dev/null && echo "kubectl ok"
kubectl get nodes

# Forge endpoints (override if your workstation uses different names/IPs)
FORGE_HOST=git.atlas.lan          # Gitea web/API + SSH hostname
NODE_IP=10.0.0.110                # any k3s node (Traefik + svclb listen here)
SSH_PORT=2222                     # Gitea SSH

# Name resolution: git.atlas.lan must resolve on the workstation.
getent hosts "$FORGE_HOST" || echo "ADD DNS: '$NODE_IP $FORGE_HOST' to Pi-hole or /etc/hosts"
# SSH reachability (host key is the Gitea Go SSH server)
ssh -p "$SSH_PORT" -o StrictHostKeyChecking=accept-new git@"$FORGE_HOST" 2>&1 | head -1
```

If `git.atlas.lan` does not resolve, add a Pi-hole record (`10.0.0.110
git.atlas.lan`) or, for a quick local fix, an `/etc/hosts` line. Until it
resolves, use `$NODE_IP` in place of `$FORGE_HOST` for every command below.

Get an admin API token (any of these):

```sh
# a) reuse the token Argo CD already uses (fastest)
TOKEN=$(kubectl -n argocd get secret repo-gitea-atlas -o jsonpath='{.data.password}' | base64 -d)
# b) or mint a fresh one
TOKEN=$(kubectl -n gitea exec deploy/gitea -- \
  gitea admin user generate-access-token -u atlas-admin -n deploy-$(date +%s) --scopes all --raw | tr -d '\r')
export GITEA_TOKEN="$TOKEN"
export API="https://$FORGE_HOST/api/v1"     # add: curl -k, or trust atlas-ca
```

API calls below use `curl -k` because the workstation may not trust `atlas-ca`.
Prefer `--cacert <(kubectl -n cert-manager get secret atlas-ca-tls -o jsonpath='{.data.tls\.crt}' | base64 -d)`
if you have it.

## Step 1 — Collect the app facts

Ask/derive and record them; the rest of the skill substitutes these:

| Variable | Example | Notes |
| --- | --- | --- |
| `APP` | `demo-app` | repo + chart + k8s resource name (lowercase, hyphens) |
| `ORG` | `atlas-admin` | Gitea owner |
| `NS` | `demo` | target namespace (usually `$APP`) |
| `PORT` | `80` | container port |
| `HOST` | `demo.atlas.lan` | ingress hostname (`$APP.atlas.lan` unless told otherwise) |
| `TAG` | `v0.1.0` | initial semver tag |
| `SRC` | `/path/to/checkout` | existing app checkout |
| `DOCKERFILE` | `Dockerfile` | path relative to repo root |

Ensure the app has a `Dockerfile` that builds and listens on `$PORT`. If it
does not, help the user create one before continuing.

## Step 2 — Create the Gitea repo and CI secrets

```sh
curl -ksS -X POST -H "Authorization: token $GITEA_TOKEN" -H "Content-Type: application/json" \
  -d "{\"name\":\"$APP\",\"private\":true,\"auto_init\":false,\"default_branch\":\"main\"}" \
  "$API/user/repos" | jq -r '.full_name // .message'

# CI needs: REGISTRY_USER, REGISTRY_TOKEN. The token grants push to the GitOps
# repo too (promotion). API expects base64-encoded values.
set_secret () { # $1=name $2=value
  curl -ksS -o /dev/null -w "$1 -> %{http_code}\n" -X PUT \
    -H "Authorization: token $GITEA_TOKEN" -H "Content-Type: application/json" \
    -d "$(printf '%s' "$2" | base64 -w0 | jq -R '{data:.}')" \
    "$API/repos/$ORG/$APP/actions/secrets/$1"
}
set_secret REGISTRY_USER "$ORG"
set_secret REGISTRY_TOKEN "$GITEA_TOKEN"
```

## Step 3 — Add the CI workflow

Create `$SRC/.gitea/workflows/build.yaml`. Substitute `APP`/`ORG`. Copy the
demo and change only the workflow name, repo path, and destination image.

```yaml
name: build
on:
  push:
    branches: [main]
    tags: ["v*"]

jobs:
  build-push:
    runs-on: ubuntu-latest
    container:
      image: docker:25-git
    env:
      REGISTRY: registry.atlas.lan
      REGISTRY_USER: ${{ secrets.REGISTRY_USER }}
      REGISTRY_TOKEN: ${{ secrets.REGISTRY_TOKEN }}
    steps:
      - name: Checkout
        run: git clone "http://oauth2:${REGISTRY_TOKEN}@gitea-http.gitea.svc.cluster.local:3000/ORG/APP.git" .

      - name: Configure registry auth
        run: |
          mkdir -p ~/.docker
          AUTH=$(printf '%s:%s' "${REGISTRY_USER}" "${REGISTRY_TOKEN}" | base64 | tr -d '\n')
          printf '{"auths":{"%s":{"auth":"%s"}}}' "${REGISTRY}" "${AUTH}" > ~/.docker/config.json

      - name: Build and push
        run: |
          set -e
          if [ "${GITHUB_REF_TYPE}" = "tag" ]; then TAG="${GITHUB_REF_NAME}"; else TAG="sha-$(echo "${GITHUB_SHA}" | cut -c1-7)"; fi
          docker build -t "${REGISTRY}/ORG/APP:${TAG}" .
          docker push "${REGISTRY}/ORG/APP:${TAG}"

      - name: Promote tag to GitOps repo
        if: startsWith(github.ref, 'refs/tags/v')
        run: |
          set -e
          TAG="${GITHUB_REF_NAME}"
          git clone "http://oauth2:${REGISTRY_TOKEN}@gitea-http.gitea.svc.cluster.local:3000/ORG/atlas.git" /tmp/gitops
          cd /tmp/gitops
          sed -i -E "s|^  tag: .*|  tag: ${TAG}|" "apps/APP/chart/values.yaml"
          git diff --quiet && exit 0
          git -c user.email=ci@atlas.lan -c user.name=atlas-ci commit -am "ci: promote APP ${TAG}"
          git push origin main
```

Replace `ORG` and `APP` literally. The promotion path `apps/APP/chart/values.yaml`
must match the chart location you create in Step 5.

## Step 4 — Add the remote and push

```sh
cd "$SRC"
git remote add atlas "ssh://git@$FORGE_HOST:$SSH_PORT/$ORG/$APP.git"   # use $NODE_IP if no DNS
git add .gitea/workflows/build.yaml
git commit -m "ci: atlas build and promote pipeline"
git push -u atlas main
```

Workstation SSH key must be registered in Gitea (one-time). If push is denied,
add the key:

```sh
curl -ksS -X POST -H "Authorization: token $GITEA_TOKEN" -H "Content-Type: application/json" \
  -d "$(jq -cn --arg k "$(cat ~/.ssh/id_rsa.pub)" '{title:"workstation",key:$k}')" \
  "$API/user/keys"
```

## Step 5 — Add the GitOps chart and Argo CD Application

In the **platform repo** (`211lab/atlas`), create `apps/$APP/chart/`.
Start from `examples/demo-app/chart` and edit:

`apps/$APP/chart/Chart.yaml`
```yaml
apiVersion: v2
name: APP
version: 0.1.0
appVersion: "1.0.0"
```

`apps/$APP/chart/values.yaml`
```yaml
image:
  repository: registry.atlas.lan/ORG/APP
  tag: v0.1.0
  pullPolicy: IfNotPresent
imagePullSecrets: gitea-registry
replicaCount: 1
service:
  port: PORT
ingress:
  enabled: true
  className: traefik
  host: HOST
  annotations:
    cert-manager.io/cluster-issuer: atlas-ca
  tlsSecretName: APP-tls
resources:
  requests: { cpu: 10m, memory: 32Mi }
  limits: { memory: 128Mi }
```

Copy `examples/demo-app/chart/templates/{deployment,service,ingress}.yaml`
verbatim (they are generic). The deployment already references
`imagePullSecrets: gitea-registry`.

Create the Argo CD Application `gitops/apps/$APP.yaml` (copy
`gitops/apps/demo-app.yaml`, change name/namespace/path):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: APP
  namespace: argocd
  finalizers: [resources-finalizer.argocd.argoproj.io]
spec:
  project: platform
  destination:
    server: https://kubernetes.default.svc
    namespace: NS
  source:
    repoURL: http://gitea-http.gitea.svc.cluster.local:3000/atlas-admin/atlas.git
    targetRevision: main
    path: apps/APP/chart
    helm:
      releaseName: APP
      valueFiles: [values.yaml]
  syncPolicy:
    automated: { prune: true, selfHeal: true }
    syncOptions: [CreateNamespace=true]
```

Give the target namespace a registry pull secret (the image is private). Seal it
so it lives in git:

```sh
AUTH=$(printf '%s:%s' "$ORG" "$GITEA_TOKEN" | base64 | tr -d '\n')
DCFG=$(jq -cn --arg a "$AUTH" '{auths:{"registry.atlas.lan":{auth:$a,username:"'"$ORG"'"}}}')
cat >/tmp/reg.yaml <<EOF
apiVersion: v1
kind: Secret
metadata: { name: gitea-registry, namespace: NS }
type: kubernetes.io/dockerconfigjson
stringData: { .dockerconfigjson: '$DCFG' }
EOF
kubeseal --controller-name sealed-secrets-controller --controller-namespace sealed-secrets \
  --format yaml </tmp/reg.yaml >gitops/sealed/$APP-registry.yaml
kubectl apply -f gitops/sealed/$APP-registry.yaml
```

## Step 6 — Push the platform changes

```sh
cd /path/to/atlas
git add apps/$APP gitops/apps/$APP.yaml gitops/sealed/$APP-registry.yaml
git commit -m "feat: add $APP chart and Argo CD application"
git push origin main        # GitHub mirror
git push gitea main         # local forge (webhook triggers Argo CD)
```

If Argo CD does not pick it up within a minute, force a refresh:

```sh
kubectl -n argocd annotate application root argocd.argoproj.io/refresh=hard --overwrite
kubectl -n argocd annotate application $APP  argocd.argoproj.io/refresh=hard --overwrite
```

## Step 7 — Release and deploy

```sh
cd "$SRC"
git tag -a "$TAG" -m "$APP $TAG"
git push atlas "$TAG"
```

The tag triggers CI: build → push to the registry → commit `image.tag=$TAG`
into `apps/$APP/chart/values.yaml` on the forge → Gitea webhook → Argo CD.

## Step 8 — Verify

```sh
export KUBECONFIG=~/.kube/atlas-admin.yaml
kubectl -n argocd get application "$APP" -o custom-columns=SYNC:.status.sync.status,HEALTH:.status.health.status
kubectl -n NS get deploy,po,ingress,certificate
kubectl -n NS get deploy "$APP" -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'

# Endpoint (use the CA or -k)
curl -ksS -o /dev/null -w "%{http_code}\n" --resolve "$HOST:443:$NODE_IP" "https://$HOST/"
```

Success = Argo Application `Synced/Healthy`, deployment Ready with the `$TAG`
image, and the endpoint returns 200.

To watch CI: `curl -ksS -H "Authorization: token $GITEA_TOKEN" "$API/repos/$ORG/$APP/actions/runs" | jq`.

## Step 9 — Change and remove

- **New release**: `git tag v0.2.0 && git push atlas v0.2.0` — never edit the
  image tag in git by hand; CI owns `apps/$APP/chart/values.yaml`.
- **Remove**: delete `gitops/apps/$APP.yaml` (and `apps/$APP`), push; Argo CD
  prunes the Application and its resources. Optionally delete the Gitea repo and
  the `gitops/sealed/$APP-registry.yaml` secret.

## Guardrails

- Never commit plaintext secrets; only SealedSecrets.
- The Gitea token is cluster-admin-scoped in Gitea — treat it as sensitive and
  seal/store it, never paste it into git or an app repo.
- Keep one Argo `AppProject` (`platform`) and the app-of-apps (`root`) as the
  only entry points; add merged apps under `gitops/apps/`.
- Chart names/resources must be unique per namespace.
- If a build does not appear, check the runner: `kubectl -n gitea get pods`,
  logs on `gitea-actions-runner-0 -c runner`.
