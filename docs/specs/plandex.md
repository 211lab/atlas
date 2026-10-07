# Plandex self-hosted server

Status: draft
Owner: —
Date: 2026-10-07

## Goal

Self-host the Plandex server on Atlas at `https://plandex.atlas.lan`, backed by
CloudNativePG PostgreSQL, so a workstation CLI can drive the terminal AI coding
agent against a LAN-reachable server that persists plans and context.

## User-visible behavior

- An operator on the LAN configures the Plandex CLI to point at
  `https://plandex.atlas.lan` and runs plans.
- Plans, context, and history survive pod restarts and rescheduling.
- Argo CD reconciles the deployment; access uses `atlas-ca` TLS and the LAN
  allowlist.

## Non-goals

- A browser UI (this spec covers the server; the CLI runs on the workstation).
- Public internet exposure.
- Multi-tenant isolation and per-user quota design.
- Configuring specific AI providers or models beyond supplying keys.

## Acceptance criteria

- Given the root app-of-apps is reconciling and the CNPG operator is installed,
  when this change is merged, then an Argo CD Application deploys the Plandex
  server plus a CNPG `Cluster` in the `plandex` namespace with automated sync and
  self-heal.
- Given a LAN client, when it reaches `https://plandex.atlas.lan`, then Traefik
  routes to the server over `atlas-ca` TLS with the `10.0.0.0/8` allowlist;
  clients outside the range are denied.
- Given the server pod is restarted or rescheduled, when it becomes ready, then
  plans and context remain available from the CNPG database.
- Given the pod template, then the database credentials come from the
  CNPG-generated Secret and AI provider keys come from SealedSecrets.
- Given a workstation CLI configured with the server host, when it connects, then
  it can create and run a plan against the server.
- Given the chart and values, when Helm rendering runs, then it renders
  successfully and includes the Deployment, Service, Ingress, database Secret
  reference, and TLS reference.

## Constraints

- In-repo chart (`apps/plandex/chart`) running the upstream `plandex-server`
  image pinned by tag, with the Postgres backend.
- Database via CNPG (`Cluster` + `Database` CRs in `apps/plandex/manifests`);
  consume the generated application Secret.
- `atlas-ca` TLS and the Traefik `10.0.0.0/8` ipallow middleware.
- AI provider keys and any server secrets are SealedSecrets only.
- Conservative sizing; the server is a single instance.

## Assumptions

- ASSUMPTION: The Plandex server is a single-instance API service backed by
  Postgres; horizontal scaling is not needed.
- ASSUMPTION: The server exposes an HTTP API suitable for an `atlas-ca` ingress
  behind the LAN allowlist; the exact port and health path are confirmed at
  implementation time.
- ASSUMPTION: AI provider keys (for example `OPENROUTER_API_KEY`) are supplied by
  the operator and sealed; the server runs without them if none are provided.
- ASSUMPTION: The CLI's TLS trust for `atlas-ca` is established on the
  workstation (trust the CA or allow the insecure flag for local use).
- ASSUMPTION: `plandex.atlas.lan` resolves via Pi-hole/hosts until ADR 0001 DNS is
  live.

## Plan

1. Confirm the upstream server image, listen port, health endpoint, and required
   environment from the Plandex self-hosting docs. Verify: notes recorded in the
   runbook.
2. Add `apps/plandex/manifests/` — CNPG `Cluster` and `Database` CR.
   Verify: cluster `Ready`; app Secret generated.
3. Add `apps/plandex/chart/` — Deployment (server image, DB env from the CNPG
   Secret, provider-key env from SealedSecrets), Service, Ingress
   (`plandex.atlas.lan`, `atlas-ca`, LAN middleware), resources. Verify:
   `helm template`.
4. Seal AI provider keys and any server secrets.
5. Add `gitops/apps/plandex.yaml` (app-of-apps with CNPG ordering). Verify:
   `Synced/Healthy` after push.
6. Add `docs/plandex.md` runbook (server + workstation CLI setup); update
   `docs/applications.md`.

## Tasks

- [ ] Confirm upstream server image, port, health path, and required env.
- [ ] Add CNPG manifests and validate.
- [ ] Add chart and render-validate.
- [ ] Seal provider keys.
- [ ] Add the Argo CD Application.
- [ ] Add runbook and update the applications catalog.
- [ ] Verify acceptance criteria (LAN HTTPS, persistence, CLI connect + run).

## Rollback

Delete `gitops/apps/plandex.yaml` (and `apps/plandex`) and push; Argo CD prunes the
resources. Preserve the CNPG cluster until data removal is explicitly approved.
Re-apply the prior revision to restore without data loss.

## Open questions / rollout checks

- Exact server image name/tag, listen port, and health endpoint.
- Whether the server requires object storage or a workspace volume beyond Postgres.
- Which provider keys to enable on first deploy.
