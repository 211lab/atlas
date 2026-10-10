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
- First-run model-provider setup is an operator action after rollout.
- LAN name resolution requires a Pi-hole/hosts entry for `odysseus.atlas.lan`
  while external DNS is unavailable.
