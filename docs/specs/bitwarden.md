# Bitwarden secrets platform (Vaultwarden + External Secrets)

Status: draft
Owner: —
Date: 2026-10-09

## Goal

Run a self-hosted Bitwarden-compatible vault on Atlas serving two distinct use
cases from one deployment:

1. **Human credentials** — the household's password manager, reachable from the
   official Bitwarden mobile apps and browser extensions over the LAN.
2. **Application secrets vault** — a machine-facing store for application
   secrets (API keys, tokens, third-party credentials) that Kubernetes consumes
   via the External Secrets Operator (ESO), with automated sync and workload
   redeploy on rotation.

## User-visible behavior

- A user opens `https://vault.atlas.lan`, logs into the web vault, and manages
  passwords, notes, and attachments.
- A user installs the official Bitwarden mobile app, sets the custom server URL
  to `https://vault.atlas.lan`, logs in, and syncs/autofills credentials on the
  phone. Sync works over LAN (and via VPN when away, if configured later).
- A platform operator stores an application secret (e.g. an n8n API key) as a
  Bitwarden item, declares an `ExternalSecret` in the app's namespace, and the
  secret materializes as a normal Kubernetes `Secret` that the app consumes.
- When the operator rotates the value in Bitwarden, ESO refreshes the
  Kubernetes `Secret` within its refresh interval, and Reloader performs a
  rolling restart of workloads that reference it, so the new value is live
  without manual `kubectl` work.
- Argo CD reconciles all of it (Vaultwarden, ESO, Reloader, `ExternalSecret`s);
  nothing is applied by hand.

## Non-goals

- Public-internet exposure of the vault (no reverse proxy from the internet;
  remote access is a later VPN concern).
- Migrating existing SealedSecrets off Sealed Secrets; both mechanisms
  coexist (see Constraints).
- Official Bitwarden Server (Java/.NET bundle with MSSQL) — too heavy for this
  cluster's memory budget.
- Bitwarden Organizations/SSO/enterprise features, Bitwarden Send, password
  policy enforcement.
- Backup/restore of the vault database beyond the standard PVC snapshot story
  (a dedicated runbook follow-up, like Immich's).

## Acceptance criteria

### Vault (human credentials)

- Given the root app-of-apps is reconciling, when this change is merged, then
  an Argo CD Application deploys Vaultwarden with automated sync and self-heal.
- Given a LAN client, when it visits `https://vault.atlas.lan`, then Traefik
  routes to Vaultwarden over `atlas-ca` TLS with the `10.0.0.0/8` ipallow
  middleware; clients outside the range are denied.
- Given the pod is restarted or rescheduled, when it comes back, then all
  vault data (accounts, ciphers, attachments) survives (persistent volume).
- Given a mobile device with the `atlas-ca` root certificate installed, when
  the official Bitwarden app is pointed at `https://vault.atlas.lan`, then
  login and sync succeed without TLS errors.
- Given the admin token, when an operator visits `/admin`, then the admin
  panel is reachable and protected (admin token from a SealedSecret).

### Application secrets vault (ESO)

- Given the External Secrets Operator is deployed, when a `ClusterSecretStore`
  references the Vaultwarden instance with credentials from a SealedSecret,
  then ESO authenticates successfully (store shows `Ready`).
- Given an `ExternalSecret` in an application namespace, when it reconciles,
  then a Kubernetes `Secret` is created/updated in that namespace with the
  keys mapped from the Bitwarden item, and Argo CD does not fight ESO over the
  generated Secret (correct ownership/ignore annotations).
- Given a secret value is rotated in Bitwarden, when ESO's refresh interval
  elapses, then the Kubernetes `Secret` reflects the new value.
- Given a Deployment consuming an ESO-managed Secret is annotated for Reloader,
  when the Secret is updated, then the Deployment performs a rolling restart
  and pods come back reading the new value.
- Given the ESO token SealedSecret, when the cluster (or a namespace) is
  rebuilt, then ESO can re-authenticate from git alone — no manual secret
  re-creation for the bootstrap path.

## Constraints

- **Vaultwarden** (single container, Rust) as the server; image pinned by tag.
  In-repo chart under `apps/vaultwarden/chart` (no trustworthy upstream chart
  precedent; matches the in-house app style).
- Data on a `truenas-nfs` PVC (SQLite database + attachments + icons). SQLite
  is the Vaultwarden default and sufficient at household scale; CNPG is not
  required (ASSUMPTION below).
- `atlas-ca` TLS and the Traefik `10.0.0.0/8` ipallow middleware, matching
  `redop` and `home-assistant`.
- **Secrets coexistence policy**: SealedSecrets remain the mechanism for
  bootstrap-critical and low-churn secrets (including the ESO↔Vaultwarden
  credentials themselves — chicken-and-egg must resolve from git). ESO +
  Bitwarden is for application secrets that benefit from central rotation.
  No plaintext secrets anywhere in git, as always.
- ESO and Reloader are platform components: upstream charts pinned in
  `gitops/apps/external-secrets.yaml` and `gitops/apps/reloader.yaml` with
  values in `helm/values/`, following the third-party-stack style.
- Sync-wave ordering: ESO (CRD-providing operator) before any `ExternalSecret`
  CRs; Vaultwarden + its store credentials before the `ClusterSecretStore`
  becomes `Ready`.
- Realistic memory requests/limits (control planes run hot; single worker).
  Vaultwarden is small (~tens of MB); ESO and Reloader are modest.
- Mobile clients must trust `atlas-ca`: the CA root cert must be installed on
  phones (documented in the runbook), or the vault is unreachable from mobile.

## Assumptions

- ASSUMPTION: Vaultwarden (Bitwarden-compatible server) is acceptable instead
  of official Bitwarden self-hosted; official mobile/desktop/browser clients
  work against it.
- ASSUMPTION: ESO's `bitwardenpw` provider (Bitwarden Password Manager client)
  is the integration path, since it speaks to Vaultwarden's Bitwarden-compatible
  API. (ESO's plain `bitwarden` provider targets Bitwarden Secrets Manager,
  which Vaultwarden does not implement.)
- ASSUMPTION: Reloader (stakater) is the redeploy trigger; Argo CD alone is not
  used to bounce workloads on secret change.
- ASSUMPTION: A single Vaultwarden replica; no HA requirement.
- ASSUMPTION: `vault.atlas.lan` resolves via Pi-hole/hosts until ADR 0001 DNS
  is live.
- ASSUMPTION: Household scale (a handful of users, dozens of items) — SQLite
  on NFS is adequate; no CNPG cluster for the vault.
- ASSUMPTION: ESO refresh interval on the order of 1h is acceptable; rotation
  propagation is not expected to be instantaneous.

## Plan

1. Add `apps/vaultwarden/chart/` — Deployment (pinned `vaultwarden/server`
   image), Service, Ingress (`vault.atlas.lan`, `atlas-ca`, LAN middleware),
   data PVC on `truenas-nfs`, `ADMIN_TOKEN` from a SealedSecret, resources.
   Verify: `helm template` renders; pod goes `Ready` after push.
2. Seal the Vaultwarden admin token into `gitops/sealed/`.
3. Add `gitops/apps/vaultwarden.yaml` (app-of-apps). Verify: `Synced/Healthy`.
4. Add ESO as a platform component: `gitops/apps/external-secrets.yaml` +
   `helm/values/external-secrets.yaml` (upstream `external-secrets` chart,
   pinned), in an earlier sync-wave. Verify: operator `Ready`, CRDs present.
5. Add Reloader: `gitops/apps/reloader.yaml` + `helm/values/reloader.yaml`
   (upstream chart, pinned). Verify: deployment `Ready`.
6. Create a Bitwarden item holding a first machine secret and a machine
   account (API client credentials) for ESO; seal the client
   id/secret/token into `gitops/sealed/` for the `ClusterSecretStore`.
7. Add a `ClusterSecretStore` (bitwardenpw provider → `vault.atlas.lan`) and
   one pilot `ExternalSecret` in a low-risk app namespace. Verify: store and
   ExternalSecret `Ready`, generated Secret contents match Bitwarden.
8. Annotate the pilot workload for Reloader; rotate the value in Bitwarden and
   observe refresh + rolling restart. Verify: new value live in the pod.
9. Add `docs/vaultwarden.md` runbook (mobile CA install, admin token, backup
   note, rotation workflow) and update `docs/applications.md` +
   `docs/gitops-platform.md` (secrets section: SealedSecrets vs ESO policy).

## Tasks

- [ ] Vaultwarden chart + SealedSecret admin token + Argo CD Application.
- [ ] ESO platform component (chart, values, Application, sync-wave).
- [ ] Reloader platform component.
- [ ] ESO machine account in Bitwarden; sealed credentials; `ClusterSecretStore`.
- [ ] Pilot `ExternalSecret` + Reloader annotation; rotation rehearsal.
- [ ] Runbook + docs updates (applications catalog, gitops-platform secrets
      policy).
- [ ] Verify acceptance criteria (web vault, mobile sync, ESO sync, rotation
      redeploy).

## Rollback

Delete `gitops/apps/vaultwarden.yaml`, `gitops/apps/external-secrets.yaml`,
`gitops/apps/reloader.yaml` (and `apps/vaultwarden`) and push; Argo CD prunes
the resources. Keep the vault PVC until data removal is explicitly approved.
Workloads revert to their SealedSecret-sourced Secrets; remove Reloader
annotations and `ExternalSecret`s in the same change so apps never reference
ESO-managed Secrets that no longer exist.

## Open questions / rollout checks

- Which app is the pilot for the first `ExternalSecret` (n8n API keys are a
  natural candidate once n8n lands)?
- Does the household want per-user accounts on the vault, or a shared
  organization/collection model?
- Remote (away-from-LAN) mobile access: VPN (e.g. WireGuard) later — confirm
  out of scope for this spec.
- Vaultwarden backup story: SQLite file on NFS — is the existing PVC snapshot
  approach sufficient, or does it need a dedicated dump job?
- Confirm ESO `bitwardenpw` provider version compatibility with the pinned
  Vaultwarden version before pinning both.
- Reloader scope: cluster-wide or namespace-scoped rollout annotations policy?
