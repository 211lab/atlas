# Paperless-ngx — document management with OCR

Status: draft
Owner: —
Date: 2026-10-07

## Goal

Deploy [Paperless-ngx](https://github.com/paperless-ngx/paperless-ngx) on Atlas at
`https://paperless.atlas.lan`, backed by CloudNativePG PostgreSQL and valkey, so
LAN users can scan, OCR, index, and retrieve documents with data that survives
restarts.

## User-visible behavior

- A LAN user opens `https://paperless.atlas.lan`, completes first-run admin setup,
  and uploads/scans documents that are OCR'd, tagged, and searchable.
- Documents, thumbnails, searchable text, tags, and accounts survive pod restarts
  and rescheduling.
- Document consumption works through the web UI (upload/drag-drop) and the
  consumption directory (in-pod) without a dedicated consumption e-mail or
  mobile-app setup.
- Argo CD reconciles the deployment; access uses `atlas-ca` TLS and the LAN
  allowlist.

## Non-goals

- Public internet exposure.
- Gotenberg/Tika sidecars for Office/attachment parsing (follow-up if needed).
- E-mail consumer automation (IMAP polling rules) or mobile-app push.
- Migrating an existing Paperless(-ng) instance.
- Custom classifiers or machine-learning tag/keyword training setup.

## Acceptance criteria

- Given the root app-of-apps is reconciling and the CNPG operator is installed,
  when this change is merged, then an Argo CD Application deploys Paperless-ngx,
  valkey, and a CNPG `Cluster` in the `paperless` namespace with automated sync
  and self-heal.
- Given a LAN client, when it visits `https://paperless.atlas.lan`, then Traefik
  routes to Paperless-ngx over `atlas-ca` TLS with the `10.0.0.0/8` allowlist;
  clients outside the range are denied.
- Given the Paperless pod is restarted or rescheduled, when it becomes ready,
  then documents, the archive, thumbnails, and the search index remain available
  (media/data/consume volumes persistent; database on CNPG; broker on valkey).
- Given the trusted proxy setup, then Paperless trusts Traefik (proxy CIDR) so
  generated URLs and CSRF checks work behind the ingress.
- Given the pod template, then the database credentials come from the
  CNPG-generated Secret and the admin bootstrap and `PAPERLESS_SECRET_KEY` come
  from SealedSecrets.
- Given the chart and values, when Helm rendering runs, then it renders
  successfully and includes the Deployment, Service, Ingress, PVCs, the CNPG and
  valkey connection settings, and the TLS reference.
- Given the backup design, when it is rehearsed, then database dumps and the
  document/media volumes restore a working, searchable instance.

## Constraints

- In-repo chart (`apps/paperless/chart`) with the upstream
  `ghcr.io/paperless-ngx/paperless-ngx` image pinned by tag.
- Database via CNPG (`Cluster` + `Database` CRs in `apps/paperless/manifests`);
  consume the generated application Secret.
- Broker via a small valkey Deployment (same pattern Immich uses in-chart), not
  a separate namespace.
- Storage: `media`, `data`, and `consume` volumes on `truenas-nfs` (media is the
  large one; consume can be small). Storage classes are immutable.
- OCR is the built-in OCRmyPDF; no GPU needed.
- `atlas-ca` TLS and the Traefik `10.0.0.0/8` ipallow middleware; trusted proxy
  must cover the reschedulable Traefik pod CIDR (`10.42.0.0/16`).
- All secrets (secret key, admin credentials) are SealedSecrets.

## Assumptions

- ASSUMPTION: "Paperless NG" means **Paperless-ngx**, the maintained successor of
  the original Paperless-ng (the original is unmaintained).
- ASSUMPTION: `paperless.atlas.lan` is the hostname (the `docs.atlas.lan` name is
  taken by the documentation site).
- ASSUMPTION: Web-UI upload is the primary consumption path; a LAN-shared
  consume folder (SMB to the NAS pointing into the consume volume) is a possible
  follow-up, not part of this spec.
- ASSUMPTION: Office/e-mail attachment parsing (Gotenberg + Tika) is deferred;
  PDF/image consumption works without them.
- ASSUMPTION: A single Paperless-ngx webserver instance plus valkey is
  sufficient; no paperless-worker scaling.
- ASSUMPTION: `paperless.atlas.lan` resolves via Pi-hole/hosts until ADR 0001
  DNS is live.

## Plan

1. Add `apps/paperless/manifests/` — CNPG `Cluster` and `Database` CR.
   Verify: cluster `Ready`; app Secret generated.
2. Add `apps/paperless/chart/` — Deployment (webserver; valkey sidecar or
   separate small Deployment), Service (port 8000), Ingress
   (`paperless.atlas.lan`, `atlas-ca`, LAN middleware), media/data/consume PVCs
   on `truenas-nfs`, DB env from the CNPG Secret, valkey env, trusted-proxy and
   CSRF settings, `PAPERLESS_SECRET_KEY` + admin bootstrap from SealedSecrets,
   resources. Verify: `helm template`.
3. Seal `PAPERLESS_SECRET_KEY` and admin bootstrap credentials.
4. **Backup design (user-data-heavy app).** Scheduled CNPG dumps plus media/data
   volume backup to a separate target with retention; rehearse a restore and
   record it in the runbook. Verify: restore rehearsal recorded.
5. Add `gitops/apps/paperless.yaml` (app-of-apps with CNPG ordering). Verify:
   `Synced/Healthy` after push.
6. Add `docs/paperless.md` runbook; update `docs/applications.md` and the
   backlog status.

## Tasks

- [ ] Add CNPG manifests and validate.
- [ ] Add chart and render-validate.
- [ ] Seal secret key + admin bootstrap.
- [ ] Add the Argo CD Application.
- [ ] Define and rehearse backup/restore.
- [ ] Add runbook and update the applications catalog.
- [ ] Verify acceptance criteria (LAN HTTPS, OCR upload, persistence, search).

## Rollback

Delete `gitops/apps/paperless.yaml` (and `apps/paperless`) and push; Argo CD
prunes the resources. Preserve the CNPG cluster, the media/data PVCs, and their
backups until data removal is explicitly approved. Re-apply the prior revision
to restore without data loss.

## Open questions / rollout checks

- Media PVC initial size and growth expectations (scans are large).
- Whether an SMB export into the `consume` folder from TrueNAS is wanted now or later.
- Confirm `PAPERLESS_SECRET_KEY` is captured in the backup/restore procedure.
- OCR language packs needed (multi-language documents?).
