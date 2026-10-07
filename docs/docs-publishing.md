# Publishing Atlas documentation

The repository's entire `docs/` tree is built with MkDocs Material, including
runbooks, ADRs and specs. Navigation is discovered from Markdown; the landing
page supplies grouped links. Search indexes the complete site. Material renders
`mermaid` fences through `pymdownx.superfences`. No diagrams are added here.

The canonical endpoint is **https://docs.atlas.lan/**; `doc.atlas.lan` is not
configured. This is an internal static site without application authentication:
review all docs for sensitive information before publishing and keep ingress
reachability restricted to the intended lab/tailnet clients.

## Local verification

Run from the repository root, after confirming `/tmp/opencode` exists. Python
environments, dependency caches and generated output must stay outside git:

```sh
ls /tmp/opencode
UV_CACHE_DIR=/tmp/opencode/uv-cache uv venv --python 3.12 /tmp/opencode/atlas-docs-venv
UV_CACHE_DIR=/tmp/opencode/uv-cache uv pip install --python /tmp/opencode/atlas-docs-venv/bin/python -r requirements-docs.txt
/tmp/opencode/atlas-docs-venv/bin/mkdocs build --strict --site-dir /tmp/opencode/atlas-docs-site
helm lint apps/docs/chart
helm template docs apps/docs/chart -n docs -f apps/docs/chart/values.yaml
docker build -f apps/docs/Dockerfile -t atlas-docs:local .
```

If PATH lacks the tools on this workstation, use `/home/wsl/.local/bin/uv` and
`/home/wsl/.local/bin/helm`. MkDocs also defaults its output to
`/tmp/opencode/atlas-docs-site`. Do not run output into `site/` in the checkout.
Strict builds fail on warnings; existing source/link defects must be handled
by their documentation owner rather than suppressing warnings in this layer.
The image build also requires `docs/index.md`; finish the landing page before
publishing rather than shipping a site without a root page.

Browser verification must inspect rendered diagrams, not just Mermaid fences.
Material 9.6.14 inserts SVGs into closed shadow roots under `.mermaid` hosts;
an empty host `innerHTML` or zero `.mermaid svg` matches does not indicate a
rendering failure. Browser automation can retain the roots by instrumenting
`attachShadow` before page load, without changing its mode, then check each
SVG's nodes, visible groups and sequence participants and capture console and
network failures. Verify all diagram pages, not only standalone SVG exports.
Material currently loads Mermaid from `https://unpkg.com/mermaid@11/dist/mermaid.min.js`,
so clients need access to that CDN. This is a runtime dependency; a successful
local static build alone does not prove browser rendering or offline support.

For an HTTP smoke test, run the image locally with the same read-only root and
capability restrictions as the chart (no cluster changes):

```sh
docker run -d --name atlas-docs-smoke --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 64m --cpus 0.1 \
  -p 127.0.0.1:18080:8080 atlas-docs:local
curl --fail http://127.0.0.1:18080/
curl --fail http://127.0.0.1:18080/search/search_index.json
docker rm -f atlas-docs-smoke
```

The root Docker context uses `apps/docs/Dockerfile.dockerignore` to allow only
build inputs. The builder copies only config, requirements and `docs/`; the
runtime receives only static output. BusyBox httpd listens on 8080 as UID/GID
65534. There is no Python runtime, writable volume, PVC, database or Kubernetes
API token. The single replica requests 5m CPU/16Mi memory and is limited to
100m CPU/64Mi memory. Traefik terminates HTTPS with an `atlas-ca` certificate
stored as `docs-tls` in namespace `docs`.

The chart deliberately reuses the dave-study Deployment, Service and Ingress
structure, replacing its hardcoded labels/container name with `docs` and routing
the Service to the named HTTP port on 8080. Resource names still follow the Helm
release name. Static serving adds non-root/read-only restrictions and a liveness
probe, without carrying over any application storage.

## CI contract

`.gitea/workflows/docs.yaml` belongs to **atlas-admin/atlas**, not a separate
docs repository. An authorized push to `main` changing docs, build inputs,
templates or this workflow builds and promotes automatically. There are no
tag, pull-request or other-branch publishing triggers. Changes only to
`apps/docs/chart/values.yaml` (including promotions/rollbacks) do not rebuild;
those are GitOps runtime configuration only.

CI fetches and checks out the full event SHA detached, verifies it is on main,
and builds that clean checkout, never a workstation's uncommitted files or the
latest moving branch tip. The Docker builder runs the strict MkDocs check; CI
then HTTP-smokes the landing page and search index before pushing.

Tags are `sha-<full-event-sha>-run-<run-id>-<attempt>`, with OCI revision metadata.
They are unique release identifiers, not `latest` or a moving branch tag. A
rerun gets a new attempt suffix. The immutable artifact identity is its manifest
digest: Gitea tags are mutable,
so deployments use the captured manifest digest, not the tag. Do not manually
reuse a tag or rerun the same attempt. Retain previous released manifests and
their blobs for rollback; digest pinning prevents replacement, not deletion.

CI captures the successful `docker push` output in its private temporary
directory without a pipeline, so push failure cannot be hidden by an extractor.
It requires exactly one digest summary matching `^sha256:[a-f0-9]{64}$`; empty,
malformed or multiple matches fail before promotion. The output contains push
progress/manifest metadata, not Docker auth configuration, and is not printed.
CI then pulls `registry.atlas.lan/atlas-admin/docs@<digest>` and checks its image
ID against the local artifact built and smoke-tested. It never resolves the
mutable tag to discover or verify the digest after pushing, so a concurrent tag
overwrite cannot redirect promotion to a different artifact. A missing manifest,
failed pull or mismatched image fails closed.

After push, CI fetches current main. If newer publishing inputs differ, it
leaves the image unpromoted and lets the newer docs run release. Otherwise it
edits `image.tag` and `image.digest` together on current main, verifies both
fields, stages only `apps/docs/chart/values.yaml`, and makes
`ci: promote docs <tag>`. Unrelated main changes and previous promotions are
preserved. A normal fast-forward-only push rejects a concurrent write; there
is no force push or blind retry. Inspect that failure and rerun the appropriate
latest publishing event after confirming its inputs are still current.
Path exclusion prevents the promotion commit from triggering another build;
it still notifies Argo CD through the existing webhook/git poll.

## Required credentials and infrastructure gates

Release preparation on **2026-10-07** configured the five repository Actions
secrets below through the verified-TLS forge API. Secret-name listing confirmed
their presence; values were never printed. No commit, push, image publication or
docs deployment was performed. Remaining live gates are distinguished below.

| Requirement | Preparation evidence / remaining gate |
| --- | --- |
| `REGISTRY_USER`, `REGISTRY_TOKEN` Actions secrets | Configured with `atlas-admin` and a dedicated `write:package` PAT for publishing; actual docs push remains untested |
| `DOCS_GIT_USER`, `DOCS_GIT_TOKEN` Actions secrets | Configured with `atlas-admin` and a separate `write:repository` PAT; API pull/push permission, HTTPS `ls-remote` and push dry-run passed; no branch protection rules were present |
| `ATLAS_CA_CERT` Actions secret | Configured from `gitea/atlas-ca` ConfigMap `ca.crt`; public root PEM only, no signing key; verified HTTPS API/git trust |
| Gitea Actions enabled, `ubuntu-latest` runner + dind | Actions enabled on `atlas-admin/atlas`; instance runner `gitea-actions-runner-0` online with `ubuntu-latest`; Docker daemon 29.5.2 responds; docs CI/outbound dependency access not yet exercised |
| Runner Docker daemon registry trust | Live dind mounts the public CA at `/etc/docker/certs.d/registry.atlas.lan/ca.crt`; insecure CIDRs contain only loopback; actual docs push is still a release gate |
| Namespace-local `docs/gitea-registry` pull Secret | Strict-scope SealedSecret authored in the docs chart with a separate `read:package` PAT; controller decryption validation passed; not reconciled/applied yet |
| k3s node registry trust/reachability | Existing platform runbook declares node trust; actual docs image pull remains a release gate |
| Argo `platform`, existing atlas source access and root app | Existing platform prerequisites; docs discovery/reconciliation must be verified after the reviewed push |
| Traefik, cert-manager `atlas-ca`, DNS and client CA trust | Existing platform prerequisites; ready docs certificate and verified-TLS landing-page response must be checked after release |
| Immutable image reference | Workflow promotes a verified manifest digest and the chart deploys `repository@sha256:...`; no immutable-tag policy is required. Actual CI digest capture/pull/promotion remains to be exercised during release |

The three new PATs have only their respective area scope, not `all`, and do not
reuse or read Argo's repository token. The live token API supports `name` and
`scopes`, not per-repository or per-package bindings. They inherit `atlas-admin`
access within that area: the promotion token is not limited to a single file or
repository, and package tokens are not limited to docs. Treat these as high-trust
CI credentials, not docs-only authorization boundaries. Existing unrelated
tokens and registry configuration were left unchanged.

The matching [Gitea 1.27.0 container implementation](https://github.com/go-gitea/gitea/blob/v1.27.0/routers/api/packages/container/manifest.go#L232-L299)
deletes and reinserts a duplicate version, rather than rejecting tag reuse.
Per-run tags avoid normal collisions but cannot prevent an authorized writer
from overwriting one. No global registry mutation or overwrite test was made.
Content-digest pinning now supplies the immutable-image contract without changing
global registry behavior. Tags remain release metadata; they are not the deployed
identity. This removes the immutable-tag-policy prerequisite, not the need to
verify a successful real CI run and retain referenced manifests for rollback.

CI uses HTTPS with certificate validation, a temporary Git askpass script and
temporary Docker auth config with restrictive permissions. Tokens are not
embedded in remote URLs, echoed, passed as Docker build arguments or copied
into images. Cleanup removes temporary auth files even on failure. Do not
enable shell tracing, upload the working directory as an artifact, reuse Argo's
credentials or grant a cluster-admin credential to this job.

Registry pull preparation was explicitly authorized for this release. The
real ciphertext is in `apps/docs/chart/templates/registry-sealed-secret.yaml`,
so Argo reconciles it with the docs chart, not the unreconciled `gitops/sealed/`
directory. Its strict scope binds both `docs` namespace and `gitea-registry`
name; do not move or rename it without resealing. Sync wave `-1` precedes the
Deployment. No plaintext Secret was persisted or applied. Live inspection found
the controller Service/Deployment named `sealed-secrets-controller` in namespace
`sealed-secrets` (contrary to the release handoff's suggested `sealed-secrets`
controller name). Use the verified Service name for sealing/validation:

```sh
kubeseal --controller-name sealed-secrets-controller --controller-namespace sealed-secrets \
  --validate < apps/docs/chart/templates/registry-sealed-secret.yaml
```

For rotation, create a fresh package-read PAT, reseal the same namespace/name,
publish the reviewed chart through GitOps, verify unsealing and image pull,
then revoke the old PAT. Do not revoke the current pull PAT before release.

## Release, verification and rollback

The initial chart tag `unreleased-bootstrap` with empty `image.digest` is
explicitly **not a published image**. The chart uses `repository:tag` only as
the empty-digest fallback and requires a nonempty tag in that case. With a
nonempty digest it uses `repository@digest`, ignoring the tag for image selection;
invalid nonempty digests fail Helm rendering rather than falling back to a tag.
Applying the Application before the first successful CI promotion and
pull-secret provisioning can produce ImagePullBackOff. This change does not
claim that an image or live documentation deployment exists.

1. Release authorization exists, but this preparation stops before committing
   or pushing for independent verification. Complete the prerequisite gates
   and review the full docs tree and diagram limits. The checkout was safely
   fast-forwarded from `fd89089` to forge `2a08871`, preserving the Redop
   promotion and all uncommitted docs. Fetch/merge `--ff-only` again immediately
   before the later publishing step; stop on conflicts or non-fast-forward.
2. Publish the reviewed changes to Gitea main through the authorized process.
   The docs push builds an image and commits its promotion; no release tag or
   separate repository is needed. Do not manually replace the bootstrap tag or
   digest; CI promotes the verified pair atomically in one values-file commit.
   The existing SSH key authenticates as `atlas-admin`; use the direct forge
   URL, not `origin` (GitHub), without adding a remote or putting tokens in URLs:

   ```sh
   git fetch ssh://git@git.atlas.lan:2222/atlas-admin/atlas.git main
   git merge --ff-only FETCH_HEAD
   git push ssh://git@git.atlas.lan:2222/atlas-admin/atlas.git HEAD:main
   ```

   These are the later release commands, not permission to bypass independent
   review. After review and only at the authorized commit step, use this exact
   staging allowlist, not directory globs or `git add .`:

   ```sh
   git add -- \
     .gitea/workflows/docs.yaml \
     mkdocs.yml \
     requirements-docs.txt \
     apps/docs/Dockerfile \
     apps/docs/Dockerfile.dockerignore \
     apps/docs/chart/Chart.yaml \
     apps/docs/chart/values.yaml \
     apps/docs/chart/templates/deployment.yaml \
     apps/docs/chart/templates/ingress.yaml \
     apps/docs/chart/templates/service.yaml \
     apps/docs/chart/templates/registry-sealed-secret.yaml \
     gitops/apps/docs.yaml \
     docs/index.md \
     docs/docs-publishing.md \
     docs/infrastructure-review.md \
     docs/architecture/placement.md \
     docs/architecture/application-dependencies.md \
     docs/adr/0001-service-naming-and-reachability.md \
     docs/applications.md \
     docs/atlas-dns.md \
     docs/c4-architecture.md \
     docs/gitops-platform.md \
     docs/kubernetes-control-plane.md \
     docs/pihole-dns.md \
     docs/pihole-runbook.md \
     docs/specs/docs-site-and-infrastructure-review.md
   git diff --cached --check
   git diff --cached --name-only
   git diff --cached
   ```

   Review each current file before staging; this allowlist is not permission to
   include concurrent edits outside the release scope. Confirm the staged paths
   match this list and contain no unrelated changes or plaintext credentials.
   Leave `docs/backlog.md` and the six unrelated specs (`atlas-landing.md`,
   `code-server.md`, `n8n.md`, `nextcloud.md`, `paperclip.md`, `paperless-ngx.md` under
   `docs/specs/`) untouched and unstaged for separate publication. Do not use
   `docs/**` or `docs/specs/**` staging globs. Verify a clean HEAD export with only
   the listed paths overlaid: run a strict MkDocs build, internal-link/search
   checks and built-site diagram verification without those seven files.
   Never force-push or reset away forge promotions.
3. Confirm the CI strict build, smoke, registry push and promotion all passed;
   inspect the resulting tag, manifest digest, revision and promotion diff.
   Confirm both values changed together and the Deployment selects the digest.
4. Let the existing root Application discover docs and Argo reconcile. Verify
   with read-only commands and a locally available public CA certificate:

```sh
kubectl -n argocd get application docs -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status
kubectl -n docs get deployment,pod,service,ingress,certificate
kubectl -n docs get deployment docs -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
curl --fail --cacert /path/to/atlas-ca.crt https://docs.atlas.lan/
```

Success requires Argo **Synced/Healthy**, a Ready Deployment at the promoted
`repository@digest`, a Ready certificate, and HTTP 200 containing the built landing page.
DNS resolution or Helm rendering alone is not deployment proof. Without
authorized publishing and prerequisites, live acceptance remains blocked.

Rollback requires an authorized git revert of the promotion commit (or a
reviewed restoration of the previous `image.tag` and `image.digest` pair) on main.
Never roll back only the tag: a nonempty digest takes precedence. Keep the digest
nonempty for released artifacts; clearing it would restore mutable-tag selection.
Values-only changes do not rebuild, and Argo converges to the retained manifest
by digest regardless of the tag's current target. Reverting
docs sources instead triggers a new build. To retire the service, remove the
docs Application through an authorized GitOps change; its finalizer prunes
docs resources. No persistent data needs migration or restoration.
