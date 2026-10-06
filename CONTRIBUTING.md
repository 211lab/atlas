# Contributing to Atlas

Atlas is a home-lab Kubernetes platform whose **entire desired state lives in
this repository**. Argo CD reconciles `gitops/apps/` (app-of-apps) from the
self-hosted Gitea forge; the GitHub repo is the collaboration mirror. See
[`AGENTS.md`](AGENTS.md) for the agent/automation contract and
[`docs/gitops-platform.md`](docs/gitops-platform.md) for the delivery pipeline.

> Golden rule: change git, let Argo CD converge the cluster. Do not `helm
> install` / `kubectl apply` platform changes by hand.

## Prerequisites

- `KUBECONFIG=~/.kube/atlas-admin.yaml` (cluster-admin; see
  [Kubernetes control plane](docs/kubernetes-control-plane.md)).
- `kubectl`, `helm`, `kubeseal` (install steps in `AGENTS.md`).
- The `origin` (GitHub) remote for reviews; `gitea` for the local forge.

Names under `*.atlas.lan` may not resolve from a workstation; use `--resolve`
against a node IP (`10.0.0.110`) or add a Pi-hole/hosts entry.

## Branching and commits

- Branch from the current `origin/main`: `feat/<topic>`, `fix/<topic>`,
  `docs/<topic>`, `ci/<topic>`, `chore/<topic>`.
- **Conventional Commits** are required (the log is the changelog):
  `type(scope): summary`, e.g.
  `feat(immich): deploy with CloudNativePG`,
  `feat(redop): restrict ingress to 10.0.0.0/8`,
  `docs: add atlas cluster recon skill and agent instructions`.
  Common types: `feat`, `fix`, `docs`, `ci`, `chore`, `refactor`.
- Keep changes scoped; split unrelated work into separate commits/PRs.
- Never commit plaintext secrets, tokens, kubeconfigs, or `.env` files.

## Making a change

**Platform component** (third-party stack: gitea, argocd, cert-manager,
sealed-secrets, monitoring):

1. `gitops/apps/<name>.yaml` — pin the chart `targetRevision`.
2. `helm/values/<name>.yaml` — pinned values, referenced via the `$values`
   multi-source ref.
3. Commit and push; Argo CD reconciles.

**In-house application** (redop, immich):

1. `apps/<app>/chart/` — the Helm chart and its `values.yaml`.
2. `gitops/apps/<app>.yaml` — an `Application` pointing at `apps/<app>/chart`.
3. CI builds images and promotes tags into the chart's `values.yaml`
   (`ci: promote <app> <tag>`); never hand-edit those tags.

**Secrets** (never plaintext in git):

```sh
kubeseal --controller-name sealed-secrets-controller \
  --controller-namespace sealed-secrets --format yaml < plain.yaml > gitops/sealed/<name>.yaml
```

**Cluster-scoped** objects go in `gitops/manifests/` (applied by `atlas-config`
into namespace `cert-manager`); namespaced objects belong with their app.

## Validate before opening a PR

```sh
# In-repo chat
helm template <app> apps/<app>/chart -n <ns> -f apps/<app>/chart/values.yaml

# Platform component (repo root)
helm template <name> <repo>/<chart> --version <ver> -n <ns> -f helm/values/<name>.yaml

# YAML sanity for raw manifests
python3 -c "import glob,yaml;[list(yaml.safe_load_all(open(f))) or print(f) for f in glob.glob('gitops/**/*.yaml',recursive=True)]"
```

After merge (or when testing on the forge), confirm reconciliation:

```sh
kubectl -n argocd get application <name> \
  -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status
kubectl -n <ns> get deploy,po,ingress,certificate
```

## Review and merge

- Open a PR against `211lab/atlas` (`origin`); keep the diff limited to the
  change and its docs.
- The platform's Argo CD watches the **Gitea** `main` branch; pushing `main`
  there (or letting the CI promotion job do it) triggers reconciliation.
- Update docs in the same PR when behavior or topology changes — `docs/` and
  `AGENTS.md` are the operational source of truth.

## Guardrails

- Never restart two control-plane nodes at once (etcd quorum).
- Mind memory: control-plane limits are overcommitted; set realistic requests.
- Stateful platform data uses `truenas-nfs` (single worker; `local-path` is for
  ephemeral/non-platform data). Storage classes are immutable.
- Sealed Secrets private key must be backed up, or committed SealedSecrets become
  undecryptable.
