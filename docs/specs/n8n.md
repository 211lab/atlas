# n8n workflow automation

Status: draft
Owner: —
Date: 2026-10-07

## Goal

Deploy n8n on Atlas at `https://n8n.atlas.lan`, backed by a CloudNativePG
PostgreSQL cluster, so workflows and credentials persist and can be reached from
the home LAN.

## User-visible behavior

- A LAN user opens `https://n8n.atlas.lan`, completes first-run owner setup, and
  builds and runs workflows in the n8n editor.
- Workflows, credentials, and execution history survive pod restarts and
  rescheduling.
- Webhooks served by n8n are reachable from LAN clients.
- Argo CD reconciles the deployment; access uses `atlas-ca` TLS and the LAN
  allowlist.

## Non-goals

- Public internet exposure or webhook ingress from the internet.
- Multi-instance/queue mode or worker scaling.
- Pre-built workflows, credentials, or integrations.
- Migrating an existing n8n database.

## Acceptance criteria

- Given the root app-of-apps is reconciling and the CNPG operator is installed,
  when this change is merged, then an Argo CD Application deploys n8n and a CNPG
  `Cluster` in the `n8n` namespace with automated sync and self-heal.
- Given a LAN client, when it visits `https://n8n.atlas.lan`, then Traefik routes
  to n8n over `atlas-ca` TLS with the `10.0.0.0/8` allowlist; clients outside the
  range are denied.
- Given the n8n pod is restarted or rescheduled, when it becomes ready, then
  workflows, credentials, and execution history remain available (database on
  CNPG; `/home/node/.n8n` on a persistent volume).
- Given the pod template, then the n8n encryption key, owner credentials, and
  database credentials come from SealedSecrets, and `N8N_ENCRYPTION_KEY` is set
  so stored credentials remain decryptable across restarts.
- Given the chart and values, when Helm rendering runs, then it renders
  successfully and includes the Deployment, Service, Ingress, PVC, a reference to
  the CNPG-generated database Secret, and the TLS reference.

## Constraints

- In-repo chart (`apps/n8n/chart`) with the official `n8nio/n8n` image pinned by
  tag; database via CNPG (`Cluster` + `Database` CRs in `apps/n8n/manifests`),
  following the Immich precedent.
- Consume the CNPG-generated application Secret; do not hand-manage the DB
  password.
- `atlas-ca` TLS and the Traefik `10.0.0.0/8` ipallow middleware.
- Secrets (encryption key, owner credentials, any integration secrets) are
  SealedSecrets only.
- `N8N_ENCRYPTION_KEY` must remain stable for the life of the data; losing it
  makes stored credentials unrecoverable.

## Assumptions

- ASSUMPTION: A single main instance (no queue mode) is sufficient.
- ASSUMPTION: CNPG is the standard Postgres; the n8n database uses it rather than
  the bundled SQLite default.
- ASSUMPTION: The `.n8n` PVC is protected from automatic prune/deletion.
- ASSUMPTION: `n8n.atlas.lan` resolves via Pi-hole/hosts until ADR 0001 DNS is live.

## Plan

1. Add `apps/n8n/manifests/` — a CNPG `Cluster` and a `Database` CR for n8n.
   Verify: `kubectl apply --dry-run=server` / CNPG reconciles to a `Ready` cluster
   and a generated app Secret.
2. Add `apps/n8n/chart/` — Deployment (`n8nio/n8n`), Service (port 5678),
   Ingress (`n8n.atlas.lan`, `atlas-ca`, LAN middleware), `.n8n` PVC on
   `truenas-nfs`, DB connection env from the CNPG Secret, `N8N_ENCRYPTION_KEY`
   from a SealedSecret, and resources. Verify: `helm template`.
3. Seal the n8n encryption key and owner credentials.
4. Add `gitops/apps/n8n.yaml` (app-of-apps; ensure CNPG sync-wave ordering).
   Verify: `Synced/Healthy` after push.
5. Add `docs/n8n.md` runbook (including the encryption-key warning); update
   `docs/applications.md`.

## Tasks

- [ ] Add CNPG `Cluster`/`Database` manifests and validate.
- [ ] Add chart and render-validate.
- [ ] Seal encryption key + owner credentials.
- [ ] Add the Argo CD Application.
- [ ] Add runbook and update the applications catalog.
- [ ] Verify acceptance criteria (LAN HTTPS, persistence, webhook reachability).

## Rollback

Delete `gitops/apps/n8n.yaml` (and `apps/n8n`) and push; Argo CD prunes the n8n
resources. Keep the CNPG cluster and the `.n8n` PVC until data removal is
explicitly approved; re-apply the prior revision to restore without data loss.

## Open questions / rollout checks

- Database sizing and whether execution pruning is configured to bound growth.
- Whether webhooks need a distinct host or path convention.
- Confirm `N8N_ENCRYPTION_KEY` is captured in the backup/restore procedure.
