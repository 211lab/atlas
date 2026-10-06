# Retire the demo-app workload

## Goal

Retire the `demo-app` service from the Atlas cluster while preserving the
central `atlas-admin/atlas` GitOps repository and unrelated applications.

## User-visible behavior

- Argo CD no longer declares or deploys `demo-app` into namespace `demo`.
- The demo-specific image-pull SealedSecret and `demo.atlas.lan` CoreDNS alias
  are removed from desired configuration.
- The demo image build/promotion workflow and example chart/source are removed;
  documentation no longer describes demo-app as a current deployed service.
- The standalone hosted Gitea repository `atlas-admin/demo-app` is deleted after
  the GitOps retirement is delivered.
- GitHub remains the canonical delivery remote for the repository. The central
  Gitea GitOps repository is retained because Argo CD uses it as its source.

## Non-goals

- Deleting the hosted `atlas-admin/atlas` Gitea repository or migrating Argo CD
  to a different source forge.
- Removing Gitea, the registry, or other applications such as Redop and Immich.
- Pruning live cluster resources by hand; use GitOps reconciliation after the
  source change is delivered to Gitea.

## Acceptance criteria

1. **Given** the app-of-apps source, **when** it reconciles, **then** it no
   longer contains the `demo-app` Application and Argo can prune that app's
   owned workload resources.
2. **Given** demo-specific support configuration, **when** the repo is
   reconciled, **then** the demo registry SealedSecret and CoreDNS alias are no
   longer declared.
3. **Given** repository contents, **when** searching deployment/build inputs,
   **then** there is no demo-app chart, image-build/promotion workflow, or
   demo-app Dockerfile/source; the separate `atlas-admin/demo-app` Gitea repo is
   also removed.
4. **Given** operational documentation, **when** reading current app inventories
   and DNS/deployment examples, **then** demo-app is not represented as an
   active service; generic examples and other app documentation remain intact.
5. **Given** the retirement change, **when** delivered, **then** the GitHub
   `main` branch and the central Gitea GitOps `main` branch contain the change,
   while the hosted central repository itself remains available.

## Constraints and assumptions

- Keep Gitea's `atlas-admin/atlas` central GitOps repo; the root Argo Application
  reads its `gitops/apps` tree and has automated pruning enabled.
- Preserve all non-demo applications and platform components.
- **ASSUMPTION:** Retiring “demo-app” includes deleting the standalone
  `atlas-admin/demo-app` Gitea repo and `examples/demo-app/`,
  its Argo Application, its demo registry SealedSecret declaration, the
  `demo.atlas.lan` CoreDNS alias, and docs that claim the app is deployed.
- **ASSUMPTION:** Argo CD's existing prune policy will remove resources it owns
  after the updated source is pushed to Gitea; do not delete cluster resources
  imperatively.
- **ASSUMPTION:** The local `gitea` remote remains configured because the
  central GitOps source is still hosted there; only the retired app's build
  artifacts/repository references are in scope.

## Plan and rollback

1. Remove the demo app's Argo Application and registry SealedSecret, and remove
   its CoreDNS hostname alias.
2. Remove the demo source/chart/build workflow and update current-state docs and
   deploy guidance to remove stale references while preserving generic guidance.
3. Push the GitOps retirement to Gitea and verify Argo no longer owns the app;
   then remove the standalone `atlas-admin/demo-app` Gitea repository.
4. Search for remaining deployment/build references and validate YAML and
   documentation consistency.
5. Push the retirement change to GitHub `main` and Gitea `main` so the declared
   source and Argo's configured source agree; confirm GitOps health after sync.
6. Roll back by recreating the demo app repo from its backup and restoring the
   removed Application, secret declaration, DNS alias, source/chart/workflow,
   and docs, then push to both remotes.

## Open questions

- None blocking. Live Argo status is not yet verified; post-push reconciliation
  is part of the delivery verification.
