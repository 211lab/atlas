# Atlas root landing page (graffiti wordmark)

Status: draft
Owner: —
Date: 2026-10-07

## Goal

Serve the Atlas root domain, `https://atlas.lan`, as a single full-bleed street-art
graffiti wordmark spelling "Atlas", deployed through the existing Argo CD GitOps
workflow and reachable from the home LAN.

## User-visible behavior

- A LAN user opening `https://atlas.lan` (or `https://www.atlas.lan`) sees the
  graffiti wordmark rendered full-bleed, with no other page chrome.
- The page loads a favicon and an Open Graph/social preview image.
- The page uses Atlas internal TLS (`atlas-ca`) and is restricted to the home LAN.

## Non-goals

- Public internet exposure, public certificates, CDN, or analytics.
- Animation, video, a CMS, or per-user content.
- Linking to other Atlas services (the root page is artwork only).
- Changing cluster, DNS, certificate, or storage infrastructure.

## Acceptance criteria

- Given the root app-of-apps is reconciling, when this change is merged, then an
  Argo CD Application deploys the landing page in its own namespace with
  automated sync and self-heal.
- Given a client on the allowed private LAN, when it visits `https://atlas.lan/`,
  then the existing Traefik ingress routes to the landing page with an `atlas-ca`
  certificate and the `10.0.0.0/8` allowlist; clients outside that range are denied.
- Given the page HTML and committed assets, when rendered, then the wordmark is
  the full-bleed hero, and a favicon and an Open Graph image are referenced and
  present in the repository.
- Given an independent visual check, when the hero image is inspected, then the
  word "Atlas" is spelled correctly and legibly.
- Given the generated artwork is committed, when the repository is inspected, then
  only the final image assets are stored (no generation script, prompt log, or API
  key is committed), and no runtime component needs an image-generation key.
- Given the selected chart and values, when Helm rendering and YAML validation run,
  then they render successfully and include the ingress and the TLS secret reference.

## Constraints

- Follow the `gitops/apps/` Argo CD Application pattern and repository Helm
  conventions; this is an in-repo chart (`apps/atlas-landing/chart`) with a static
  nginx image (in-repo `Dockerfile` built by Gitea Actions) or a pinned upstream
  nginx image serving committed static files.
- Follow Atlas internal TLS (`atlas-ca`) and LAN-only ingress conventions,
  including the Traefik `10.0.0.0/8` ipallow middleware.
- No persistent storage is required.
- Do not commit credentials or keys. Never place an OpenRouter API key in the repo.
- The apex host `atlas.lan` is not covered by any wildcard; it needs an explicit
  ingress host, certificate, and DNS record.

## Assumptions

- ASSUMPTION: `atlas.lan` (apex) and `www.atlas.lan` are the acceptable hostnames.
- ASSUMPTION: The artwork is generated ahead of time by a sub-agent using
  OpenRouter's `google/gemini-nano-banana-2.1` model; the OpenRouter key is read
  transiently from the cluster `redop-secrets` Secret at authoring time and is
  never written to the repository.
- ASSUMPTION: Image models render short text unreliably, so the pipeline either
  (a) verifies spelling with a vision check, or (b) composites the exact word
  "Atlas" as SVG/text over generated texture. Spelling correctness is an
  acceptance criterion regardless of method.
- ASSUMPTION: Three candidate art directions are generated; the operator selects
  one to refine before the final hero, favicon, and Open Graph image are committed.
- ASSUMPTION: `atlas.lan` currently resolves only via workstation hosts entries or
  in-cluster CoreDNS; a Pi-hole/hosts entry is required for LAN clients until
  ADR 0001 DNS is live.

## Plan

1. **Art forge (authoring-time, outside git).** A `general` sub-agent pulls the
   OpenRouter key from the live `redop-secrets` Secret, generates three "Atlas"
   graffiti-lettering directions with `google/gemini-nano-banana-2.1` into
   `/tmp/opencode`, runs a vision check for style and legible spelling, and
   presents them for selection. The chosen direction is refined into a hero image,
   a favicon, and an Open Graph image. Verify: spelling confirmed by vision check;
   only final assets staged for commit. Rollback: discard `/tmp` artifacts.
2. **Chart and static assets.** Add `apps/atlas-landing/chart/` (Deployment,
   Service, Ingress for `atlas.lan` + `www.atlas.lan` with `atlas-ca` TLS and the
   LAN ipallow middleware, resources requests/limits) and the committed static
   assets (HTML, hero, favicon, OG image). Verify: `helm template atlas-landing
   apps/atlas-landing/chart -n atlas-landing -f apps/atlas-landing/chart/values.yaml`.
3. **Argo CD Application.** Add `gitops/apps/atlas-landing.yaml` using the
   app-of-apps pattern. Verify: Application appears and reconciles after push.
4. **Docs.** Add `docs/atlas-landing.md` (runbook) describing the implementation,
   asset regeneration, rollout, and rollback; update `docs/applications.md`.
   Verify: links resolve and `mkdocs build` succeeds.

## Tasks

- [ ] Forge three art directions and select one (sub-agent + vision check).
- [ ] Refine and commit hero + favicon + Open Graph assets.
- [ ] Add `apps/atlas-landing/chart` and render-validate.
- [ ] Add `gitops/apps/atlas-landing.yaml`.
- [ ] Add `docs/atlas-landing.md`; update `docs/applications.md`.
- [ ] Verify acceptance criteria (rendering, LAN HTTPS, spelling, no secrets).

## Rollback

Delete `gitops/apps/atlas-landing.yaml` (and `apps/atlas-landing`) and push; Argo CD
prunes the Application and its resources. No persistent data is involved. Re-apply
the prior Git revision to restore the previous root page.

## Open questions / rollout checks

- Exact visual direction (proposed by the forge step and chosen by the operator).
- Whether an in-repo nginx `Dockerfile` is used or a pinned upstream nginx image
  serves the committed files.
- Apex certificate: confirm cert-manager can issue for a non-wildcard apex host
  and that the DNS/hosts entry for `atlas.lan` exists on LAN clients.
