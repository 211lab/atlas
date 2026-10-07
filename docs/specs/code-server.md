# code-server (VS Code in the browser)

Status: draft
Owner: —
Date: 2026-10-07

## Goal

Deploy Coder `code-server` on Atlas at `https://code.atlas.lan` so a LAN user can
edit code from a browser, with a persistent workspace that survives pod restarts.

## User-visible behavior

- A LAN user opens `https://code.atlas.lan`, authenticates with a password, and
  uses the VS Code editor in the browser.
- The workspace (files and most editor state) survives pod restarts and
  rescheduling.
- Argo CD reconciles the deployment; access uses `atlas-ca` TLS and the LAN
  allowlist.

## Non-goals

- Multi-user accounts, SSO, or per-user isolation (single-user instance).
- Public exposure.
- Installing language toolchains or extensions as part of this scope.
- Replacing the workstation development environment.

## Acceptance criteria

- Given the root app-of-apps is reconciling, when this change is merged, then an
  Argo CD Application deploys `code-server` in its own namespace with automated
  sync and self-heal.
- Given a LAN client, when it visits `https://code.atlas.lan`, then Traefik routes
  to `code-server` over `atlas-ca` TLS, the `10.0.0.0/8` allowlist applies, and a
  login is required; clients outside the range are denied.
- Given the pod is restarted or rescheduled, when it becomes ready, then the
  workspace contents remain available from the persistent volume.
- Given the pod template, then it receives the password from a SealedSecret (never
  plaintext in git) and Resources `requests`/`limits` are set.
- Given the chart and values, when Helm rendering runs, then it renders
  successfully and includes the Deployment, Service, Ingress, PVC, and TLS
  reference.

## Constraints

- Follow the in-repo chart pattern (`apps/code-server/chart`) with the upstream
  `codercom/code-server` image pinned by tag.
- Persistent workspace on `truenas-nfs` (`ReadWriteOnce`); do not rely on the
  container filesystem.
- `atlas-ca` TLS and the Traefik `10.0.0.0/8` ipallow middleware.
- Password is a SealedSecret only.
- Conservative sizing: control-plane memory is tight and there is a single worker.

## Assumptions

- ASSUMPTION: A single-user instance is sufficient; no multi-user auth is needed.
- ASSUMPTION: `truenas-nfs` is suitable for a single-writer workspace volume.
- ASSUMPTION: The workspace PVC is protected from automatic prune/deletion so a
  chart removal does not destroy data.
- ASSUMPTION: `code.atlas.lan` resolves via Pi-hole/hosts until ADR 0001 DNS is live.

## Plan

1. Add `apps/code-server/chart/` — Deployment (`codercom/code-server`), Service
   (port 8080), Ingress (`code.atlas.lan`, `atlas-ca`, LAN middleware),
   `ReadWriteOnce` PVC on `truenas-nfs`, resources, and `imagePullSecrets` if the
   image is mirrored to the internal registry. Verify: `helm template`.
2. Add a `code-server` password SealedSecret under `gitops/sealed/`.
   Verify: `kubeseal` round-trip; controller decrypts to a namespace Secret.
3. Add `gitops/apps/code-server.yaml` (app-of-apps). Verify: Application
   `Synced/Healthy` after push.
4. Add `docs/code-server.md` runbook; update `docs/applications.md`.

## Tasks

- [ ] Add chart and render-validate.
- [ ] Seal the password and add the registry pull secret if needed.
- [ ] Add the Argo CD Application.
- [ ] Add runbook and update the applications catalog.
- [ ] Verify acceptance criteria (LAN HTTPS, login, persistence).

## Rollback

Delete `gitops/apps/code-server.yaml` (and `apps/code-server`) and push; Argo CD
prunes the resources. Preserve the workspace PVC until the operator explicitly
approves data removal; re-apply the prior revision to restore without data loss.

## Open questions / rollout checks

- Workspace PVC size (initial 10Gi) and whether extensions/toolchains inflate it.
- Whether to mirror the image into `registry.atlas.lan` for supply-chain clarity.
