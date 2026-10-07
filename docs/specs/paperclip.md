# Paperclip — AI agent orchestration

Status: draft
Owner: —
Date: 2026-10-07

## Goal

Deploy [Paperclip](https://github.com/paperclipai/paperclip) on Atlas at
`https://paperclip.atlas.lan` in authenticated mode, backed by CloudNativePG
PostgreSQL and persistent file/workspace storage, so a LAN operator can run and
govern a team of AI agents and their history survives restarts.

## User-visible behavior

- A LAN operator opens `https://paperclip.atlas.lan`, signs in, creates an
  organization, hires agents, and runs tasks.
- Companies, agents, tasks, skills, secrets references, cost records, activity,
  uploads, and agent workspace data survive pod restarts and rescheduling.
- Agent runs execute in the Paperclip container using configured provider API keys.
- Argo CD reconciles the deployment; access uses `atlas-ca` TLS and the LAN
  allowlist.

## Non-goals

- Public internet exposure.
- Configuring specific agents, providers, connectors, or workflows.
- Multi-organization governance policy design.
- Custom sandbox providers (Modal, Daytona) or cloud sync.
- Replacing the cluster's existing AI tooling.

## Acceptance criteria

- Given the root app-of-apps is reconciling and the CNPG operator is installed,
  when this change is merged, then an Argo CD Application deploys Paperclip and a
  CNPG `Cluster` in the `paperclip` namespace with automated sync and self-heal.
- Given a LAN client, when it visits `https://paperclip.atlas.lan`, then it is
  required to authenticate (authenticated mode, not trusted local loopback),
  Traefik routes over `atlas-ca` TLS with the `10.0.0.0/8` allowlist, and clients
  outside the range are denied.
- Given the pod is restarted or rescheduled, when it becomes ready, then
  `PAPERCLIP_HOME` contents (assets, secrets key, agent workspaces) and the
  database remain available from persistent storage.
- Given the pod template, then provider API keys and the secrets-encryption key
  come from SealedSecrets, and the application does not receive cluster-admin
  credentials.
- Given agent runs are arbitrary workloads triggered by the app, then a
  NetworkPolicy restricts the Paperclip pod's egress to what the spec allows and
  documents the trust boundary.
- Given the chart and values, when Helm rendering runs, then it renders
  successfully and includes the Deployment, Service, Ingress, PVC, the CNPG
  database Secret reference, and the TLS reference.

## Constraints

- In-repo chart (`apps/paperclip/chart`) running the upstream Paperclip production
  Docker image (`docker build --target production`; listen on port 3100) pinned by
  tag. Do not use the `-cloud` image variant.
- Authenticated deployment mode; never bind to trusted local loopback for a LAN
  service.
- Database via CNPG (`Cluster` + `Database` CRs); file storage local PVC by
  default, S3-compatible optional later.
- Persistence: mount `PAPERCLIP_HOME` to a PVC so the embedded secrets key and
  agent workspaces are retained; if using external Postgres, the embedded
  database directory is unused but the assets, key, and workspaces still persist.
- Secrets (provider API keys, secrets key) are SealedSecrets only.
- Sizing is conservative: agent harness runs can be heavy; set realistic
  `requests`/`limits` and validate against the cluster memory budget.

## Assumptions

- ASSUMPTION: The upstream production Docker image is the runtime; Node/pnpm are
  not installed on the cluster.
- ASSUMPTION: `PAPERCLIP_HOME` (assets, secrets key, workspaces) is a good fit for
  a `truenas-nfs` PVC, and the CNPG database is the system of record.
- ASSUMPTION: The secrets-encryption key is derived from/persisted with the
  `PAPERCLIP_HOME` volume; it must be part of the backup and restore procedure.
- ASSUMPTION: Agent harness adapters (claude/codex/opencode/gemini) are enabled
  only as far as their provider API keys are supplied; the app runs without them.
- ASSUMPTION: `paperclip.atlas.lan` resolves via Pi-hole/hosts until ADR 0001 DNS
  is live.

## Plan

1. **Security review first.** Document the runner trust boundary: agent runs
   execute code, so define the NetworkPolicy, the absence of cluster-admin
   credentials, and which secrets the pod may read. Verify: review notes recorded
   in the runbook.
2. Add `apps/paperclip/manifests/` — CNPG `Cluster` and `Database` CR.
   Verify: cluster reaches `Ready`; app Secret generated.
3. Add `apps/paperclip/chart/` — Deployment (port 3100, `HOST=0.0.0.0`,
   `PAPERCLIP_HOME` volume), Service, Ingress (`paperclip.atlas.lan`, `atlas-ca`,
   LAN middleware), PVC, NetworkPolicy, DB env from the CNPG Secret, resources.
   Verify: `helm template`.
4. Seal provider API keys and any instance secrets.
5. Add `gitops/apps/paperclip.yaml` (app-of-apps with CNPG ordering). Verify:
   `Synced/Healthy` after push.
6. **Backup design (required for this spec).** Define CNPG backups (scheduled
   dumps to an NFS/S3 target) plus a `PAPERCLIP_HOME` PVC backup, with retention
   and a rehearsed restore. Verify: a restore rehearsal recorded in the runbook.
7. Add `docs/paperclip.md` runbook; update `docs/applications.md`.

## Tasks

- [ ] Record the runner/security review and NetworkPolicy design.
- [ ] Add CNPG manifests and validate.
- [ ] Add chart and render-validate.
- [ ] Seal provider API keys and instance secrets.
- [ ] Add the Argo CD Application.
- [ ] Define and rehearse backup/restore.
- [ ] Add runbook and update the applications catalog.
- [ ] Verify acceptance criteria (LAN HTTPS + auth, persistence, egress policy).

## Rollback

Delete `gitops/apps/paperclip.yaml` (and `apps/paperclip`) and push; Argo CD
prunes the resources. Preserve the CNPG cluster, the `PAPERCLIP_HOME` PVC, and
their backups until data removal is explicitly approved. Re-apply the prior
revision to restore without data loss.

## Open questions / rollout checks

- `PAPERCLIP_HOME` volume size and whether agent workspaces need their own volume.
- Whether file storage stays local to the PVC or moves to S3-compatible storage.
- Provider keys to enable on first deploy (OpenRouter, Anthropic, OpenAI, Gemini).
- Whether the runner needs additional egress (git hosts, package registries) and
  how to allowlist it safely.
