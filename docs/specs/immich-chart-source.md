# Immich OCI chart source correction

## Goal

Allow Argo CD to resolve the already-pinned public Immich Helm chart so it can
render and reconcile the initial Immich deployment.

## User-visible behavior

The Immich Application continues to use chart `immich` version `0.13.2` and the
existing values/manifests, but Argo CD fetches the chart from the correct OCI
repository path instead of receiving a chart-pull `403` and reporting sync
status `Unknown`.

## Non-goals

- Do not change the chart or Immich image version, values, ingress, PostgreSQL
  configuration, or initial NFS storage design.
- Do not include the separate PostgreSQL Restic-backup follow-up.
- Do not manually apply or install application resources in Kubernetes.

## Acceptance criteria

- **Given** an Argo CD source with chart `immich` at version `0.13.2`,
  **when** it resolves the OCI source, **then** the repository path is
  `ghcr.io/immich-app/immich-charts` (without a trailing `/immich`) and the
  resulting artifact path is
  `immich-app/immich-charts/immich:0.13.2`.
- **Given** the corrected source, **when** Argo CD refreshes the Immich
  Application, **then** manifest generation no longer fails with the duplicated
  `.../immich/immich` GHCR path or chart-pull 403.
- **Given** the fixed source is pushed to both remotes, **when** Argo CD
  reconciles the GitOps repository, **then** the Immich Application advances
  beyond `Unknown` and begins reconciling the declared initial resources.

## Constraints and assumptions

- Keep the current chart pin at `0.13.2` and the values' Immich image pin at
  `v3.2.0`.
- Preserve the current initial deployment design, including its NFS-backed
  PostgreSQL PVC; storage changes are out of scope for this correction.
- **ASSUMPTION:** GitHub Container Registry remains publicly readable from the
  Argo CD repo-server. The chart manifest endpoint for the corrected path
  returned HTTP 200 from the operator workstation; cluster access is verified
  by Argo reconciliation.

## Plan and rollback

1. Change only `repoURL` in `gitops/apps/immich.yaml` to the parent OCI
   repository; retain `chart: immich` and version `0.13.2`.
2. Verify the diff contains no chart/value/storage changes and that Argo no
   longer reports a duplicated-path chart-pull error.
3. Push the same commit to GitHub `main` and Gitea `main`.

Rollback is a revert of the repo URL correction on both `main` branches. This
returns to the previous chart-pull failure without changing application data.

## Open questions

None.
