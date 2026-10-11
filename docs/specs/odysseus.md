# Odysseus on Atlas

Status: deployed (2026-10-10)
Owner: —
Date: 2026-10-10

## Goal

Deploy the Odysseus self-hosted AI workspace from `odysseus-dev/odysseus` to
Atlas as a GitOps-managed application, reachable at
`https://odysseus.atlas.lan`.

## User-visible behavior

- A LAN user can reach Odysseus over HTTPS at `odysseus.atlas.lan`.
- The web application and its ChromaDB, SearXNG, and ntfy supporting services
  run in the `odysseus` namespace.
- Persistent application data survives pod restarts/rescheduling.
- Argo CD owns the workload and reconciles declared state from the Atlas repo.
- Authentication remains enabled; no localhost authentication bypass is enabled.

## Non-goals

- Public internet exposure.
- Configuring or provisioning an LLM provider account/API credential.
- Importing existing Odysseus user data or credentials.
- Modifying the upstream GitHub repository.
- Promising complete AI functionality before an operator configures a model
  provider through the application's supported setup.

## Acceptance criteria

- Given the Atlas root Application is reconciling, when the deployment is
  declared, then Argo CD manages an `odysseus` Application in the `odysseus`
  namespace with automated sync and self-heal.
- Given a LAN client, when it requests `https://odysseus.atlas.lan`, then
  Traefik routes to the application using an `atlas-ca` TLS certificate.
- Given a pod restart/reschedule, when the app and its dependencies recover,
  then configured persistent data remains available from persistent volumes.
- Given the application is network-accessible, then its authentication is
  enabled and `LOCALHOST_BYPASS` is false.
- Given registry credentials or application credentials are required, then
  only SealedSecrets are committed; no plaintext secret is present in git.
- Given the chart and values, when Helm rendering is run, then the app,
  supporting services, Services, PVCs, and HTTPS Ingress render successfully.
- Given the deployment rollout completes, when checking Argo CD and the
  endpoint, then the Application is `Synced/Healthy`, app pod is Ready, and the
  HTTPS endpoint returns a successful response.

## Constraints

- Use Atlas GitOps conventions: in-repo Helm chart at `apps/odysseus/chart`,
  Argo CD Application at `gitops/apps/odysseus.yaml`, encrypted secrets only.
- App container listens on port 7000.
- Hostname is `odysseus.atlas.lan`; TLS uses the `atlas-ca` ClusterIssuer.
- Follow upstream image/build/runtime requirements and keep resource requests
  conservative for the single worker and memory-constrained control plane.
- Do not perform imperative workload installation with `kubectl apply` or
  `helm install`.

## Assumptions

- ASSUMPTION: Deploy the full Compose-equivalent service set (Odysseus,
  ChromaDB, SearXNG, ntfy) inside the namespace, replacing Compose networking
  and bind mounts with Kubernetes Services and PVCs.
- ASSUMPTION: Use `truenas-nfs` for persistent app/vector data unless upstream
  compatibility or available storage evidence requires a different class; make
  storage sizes explicit and avoid ephemeral storage for user data.
- ASSUMPTION: Use the default internal Atlas CA and LAN-only routing; external
  DNS remains out of scope because Pi-hole/ExternalDNS is not operational.
- Recon found the upstream default branch is `dev`; GitHub `HEAD`/`dev` was
  `a8c147b238db01dbd00b57774ed8b453f1e43971`. The chart builds this immutable
  commit rather than assuming `main` is the upstream default branch.
- ASSUMPTION: The operator completes first-run setup and supplies model provider
  credentials in the application after deployment; no LLM secret is fabricated.
- First-run setup: create the initial Odysseus account and configure a model
  provider/model credential through the application; no provider credential is
  provisioned by this deployment.
- ASSUMPTION: `odysseus.atlas.lan` may need a LAN DNS/hosts mapping until the
  Atlas Pi-hole work is operational.

## Plan

1. Inspect upstream deployment documentation, image/Docker build and health
   behavior; confirm current Atlas chart and sealing conventions. (Complete;
   recon recorded `dev` at `a8c147b238db01dbd00b57774ed8b453f1e43971`.)
2. Add the Odysseus Helm chart and values for app plus required supporting
   services, internal service discovery, persistent volumes, auth-safe config,
   and ingress. Verify with `helm template` and static manifest checks. (Chart
   added; render verified.)
3. Add the Argo CD Application and registry pull-secret SealedSecret if using
   the private Atlas registry. Both are added; the SealedSecret validates
   against the live Atlas controller certificate. It will be decrypted when
   Argo reconciles the app.
4. Provision the Gitea source/build repo and CI workflow. The private Gitea
   repo/secrets exist and the workflow checks out `GITHUB_SHA` from Gitea using
   `REGISTRY_TOKEN`, then verifies `HEAD` before building. It builds the exact
   Gitea commit and pushes a `sha-<full-commit>` image. The workflow commit is
   local-only until the source branch is pushed.
5. Push platform changes to the configured Git remotes to activate app-of-apps
   reconciliation; push/tag the source repo to start CI and promote the pinned
   image SHA into GitOps.
6. Watch CI and Argo CD; verify pods, PVCs, ingress/certificate, and HTTPS
   endpoint. Record any model-provider or DNS follow-up.

## Rollback

Remove `gitops/apps/odysseus.yaml` and push the platform repo to prune the
Application/workloads. Preserve PVCs and SealedSecrets until data deletion is
explicitly approved; retain the previous Git revision for restoration.

## Open questions / rollout checks

- Rollout verified 2026-10-10: Argo `odysseus` and `root` are `Synced/Healthy`;
  all four Deployments Ready; PVCs Bound; `odysseus-tls` issued by `atlas-ca`;
  `https://odysseus.atlas.lan/` returns 302 → `/login` (200) with the login page.
- The Gitea Actions dind scratch cap was raised from 15Gi to 30Gi
  (`helm/values/gitea-actions.yaml`) because this image plus its build cache
  exceeded 15Gi and evicted the runner mid-build.
- Hardening (2026-10-10): the app's first boot (npm ci + Chromium + uvicorn,
  ~1.5 GiB spike) exhausted cp1's then-4 GiB guest and took the node NotReady;
  the whole odysseus stack is now pinned to the worker via
  `nodeSelector: atlas.cluster/node-type=worker` (chart values). All four k3s
  guests were resized to 4 vCPU/12 GiB on the Proxmox hosts the same day.
- First-run model-provider setup is an operator action after rollout.
- LAN name resolution requires a Pi-hole/hosts entry for `odysseus.atlas.lan`
  while external DNS is unavailable.

## Follow-up: admin credential escrow and recovery

### Goal and user-visible behavior

Keep the currently verified Odysseus `admin` login in a strict-scope
SealedSecret in the `odysseus` namespace, and document how an operator can
retrieve it or recover access if the application password drifts. The credential
is an operator-held escrow value; it is not injected into the app container.

### Non-goals

- No auth bypass, signup enablement, or additional Odysseus users.
- No automatic synchronization from the application database back into the
  Kubernetes Secret.
- No promise that the sealed password stays valid after an in-app password
  change; the application auth file remains authoritative.
- No changes to the Odysseus application or upstream source.

### Acceptance criteria (Given/When/Then)

- Given the existing `odysseus` Argo Application, when the SealedSecret is
  reconciled, then it creates `odysseus-admin-credentials` in namespace
  `odysseus` with `username` and `password` keys.
- Given this repo is inspected, when searching tracked files, then only encrypted
  credential material is present; no plaintext username/password pair is
  committed.
- Given an operator needs the credential, when following the Odysseus runbook,
  then the operator can safely retrieve the Secret and is warned that it may be
  stale after changing the password in Odysseus.
- Given an operator is locked out, when following the recovery runbook, then it
  explains that no upstream admin-reset command is documented, preserves a
  backup of `/app/data/auth.json`, resets only the existing admin password,
  invalidates persisted sessions, restarts and verifies Odysseus, and reseals
  the resulting credential.
- Given the runbook's unsupported direct auth-file operation is needed, then it
  explicitly warns that this is a manual state mutation and requires a backup
  and careful verification; it does not disable authentication or delete user
  data.

### Constraints

- Follow `docs/sealing-secrets.md`: strict scope, controller `sealed-secrets`,
  namespaced secret beside the app's other SealedSecrets, and never commit or
  apply plaintext.
- Argo CD remains the declarative owner; no plaintext Secret manifest or
  credential env vars are added to the chart.
- Recovery must preserve all existing Odysseus data and account metadata except
  the selected admin password hash and saved session tokens.

### ASSUMPTIONs

- ASSUMPTION: use Secret name `odysseus-admin-credentials` and keys `username`
  and `password`; these are for operator retrieval only.
- ASSUMPTION: the current verified admin login is appropriate to escrow; rotate
  it in Odysseus and reseal if it was shared or changed.
- ASSUMPTION: recovery documentation belongs in a dedicated
  [`docs/runbooks/odysseus.md`](../runbooks/odysseus.md) file linked from this
  spec.

### Plan and verification

1. Add the strict-scope SealedSecret at `gitops/sealed/odysseus/admin-credentials.yaml`;
   verify its encrypted payload does not expose the password and its scope/name/
   namespace match the intended Secret.
2. Add `docs/runbooks/odysseus.md` with retrieval, drift, backup, reset, rollout,
   verification, and resealing instructions; verify commands and cautionary
   notes against the deployed PVC layout and pinned upstream auth implementation.
3. Link the runbook and update this spec's rollout notes; verify YAML parses,
   docs contain no credential values, and the existing chart render remains
   unchanged.

### Rollback

Revert the runbook/spec changes and remove the SealedSecret from GitOps. Do not
delete the live Secret or persistent application data without separate explicit
approval. If a recovery password was changed, preserve access by resealing the
known-good value before removing its SealedSecret.
