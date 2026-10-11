# Atlas service directory and landing page

Status: implemented
Owner: Atlas
Date: 2026-10-11

> Implemented as a Homepage instance with Kubernetes Ingress annotation
> discovery (`gethomepage.dev/enabled`) rather than custom discovery. See
> [docs/runbooks/atlas-landing.md](../runbooks/atlas-landing.md). The weather
> background generator was added after this spec.

## Goal

Turn the existing Atlas root page into a self-updating home page that organizes
Atlas ingress routes and provides a clear place for future components. Deploy it
on the Atlas cluster through the existing Argo CD GitOps workflow and keep it
reachable from the home LAN.

## User-visible behavior

- A LAN user opening `https://atlas.lan` or `https://www.atlas.lan` sees an Atlas
  landing page with an organized directory of currently routable Atlas services.
- The directory is populated from Kubernetes Ingress resources, not a manually
  maintained list. It updates when eligible Ingresses are added, changed, or
  removed, without rebuilding the site or editing page content.
- Each listed service shows a display name, hostname/link, and category when
  available. Categories provide useful default grouping, including an
  uncategorized group for routes without optional metadata.
- Existing Atlas wordmark/artwork remains part of the page, but does not prevent
  the directory from being useful.
- The page uses Atlas internal TLS (`atlas-ca`) and remains LAN-restricted.

## Non-goals

- Public internet exposure, public certificates, CDN, analytics, or user accounts.
- A general-purpose CMS, manually maintained catalog as the source of truth,
  health monitoring, or uptime claims about listed services.
- Discovering services that have no Kubernetes Ingress.
- Changing cluster DNS, certificate, or storage infrastructure.

## Acceptance criteria

1. **GitOps deployment:** Given the root app-of-apps is reconciling, when this
   change is merged, then an Argo CD Application deploys the page in its own
   namespace with automated sync and self-heal.
2. **LAN ingress:** Given a client on the allowed private LAN, when it visits
   `https://atlas.lan/`, then Traefik routes to the page with an `atlas-ca`
   certificate and the existing `10.0.0.0/8` allowlist; clients outside that
   range are denied.
3. **Ingress discovery:** Given eligible Kubernetes Ingresses exist, when the
   page loads or an Ingress is added, changed, or deleted, then the directory
   reflects current eligible routes without a site rebuild or manual catalog
   edit. Automated tests demonstrate add/update/delete behavior.
4. **Safe filtering:** Given an Ingress has no hostname or a host outside the
   configured Atlas domain, when discovery runs, then it is omitted. The page
   does not expose arbitrary Ingress annotations or backend details.
5. **Useful organization:** Given routes have optional display-name/category
   metadata, when shown, then they are grouped and labeled using it; routes
   without metadata receive readable hostname-based labels in a default group.
6. **Least privilege:** Given discovery runs in the cluster, when permissions are
   inspected, then it has only the read-only Kubernetes API access needed to
   list/watch Ingresses cluster-wide, and no access to Secrets, write operations,
   or unrelated resource types.
7. **Resource safety:** Given the chart is rendered, then the discovery workload
   has explicit bounded resource requests/limits and health probes, and its
   ServiceAccount/RBAC, Deployment, Service, and Ingress follow Atlas conventions.
8. **Validation:** Given the implementation and chart, when Helm rendering,
   application tests, and static checks run, then they pass and cover filtering,
   fallback labels/categories, and reconciliation behavior.

## Constraints

- Preserve the existing `apps/atlas-landing` identity and hostnames. Follow
  `gitops/apps/` Argo CD and in-repo chart conventions.
- Discovery must be a runtime mechanism deployed on Atlas; build-time generation
  is insufficient for self-updating behavior.
- Follow Atlas internal TLS (`atlas-ca`) and LAN-only ingress conventions,
  including Traefik's `10.0.0.0/8` ipallow middleware.
- No persistent storage or external credentials are required.
- Do not grant discovery permissions beyond read-only list/watch for Ingresses.
- `atlas.lan` is not covered by a wildcard; it needs an explicit ingress host,
  certificate, and DNS record.

## Assumptions

- ASSUMPTION: `atlas.lan` and `www.atlas.lan` remain the user-facing hostnames;
  repository docs report LAN Pi-hole DNS and ExternalDNS are operational.
- ASSUMPTION: Kubernetes Ingress is authoritative because the request is to
  organize ingress routes; services without Ingresses are intentionally omitted.
- ASSUMPTION: Cluster-wide list/watch of Ingress resources is acceptable when
  RBAC is narrowly scoped to that resource and read-only.
- ASSUMPTION: Optional Ingress annotations supply friendly title/category, with
  hostname-based fallback. Exact annotation keys and category taxonomy are
  implementation decisions and must be documented.
- ASSUMPTION: Only hosts under `atlas.lan` are eligible; `www.atlas.lan` and the
  landing page's own Ingress should not appear as directory entries by default.

## Ordered plan, exact areas, verification, rollback

1. **Runtime discovery:** inspect existing app image/build patterns and implement
   discovery and focused automated tests in `apps/atlas-landing/`. Verify tests
   cover eligible filtering, metadata/fallback, add/update/delete, and exclusion
   of the landing page's own route. Rollback: revert discovery source and its
   image promotion.
2. **Chart, RBAC, and UI:** update `apps/atlas-landing/chart/` for the runtime
   service, narrowly scoped ServiceAccount/RBAC, bounded resources/probes, and
   page presentation. Verify Helm rendering, RBAC scope assertions, TLS and
   middleware, plus a local UI/API smoke test. Rollback: revert chart and assets.
3. **GitOps/delivery:** update `gitops/apps/atlas-landing.yaml` only if needed;
   follow existing image promotion conventions. Verify Application source and
   promoted image are consistent. Rollback: restore the previous image/chart
   values through GitOps.
4. **Documentation:** update `docs/atlas-landing.md`, `docs/applications.md`, and
   this spec with discovery behavior, metadata contract, operations, and rollback.
   Verify links and documentation build.
5. **Independent verification:** render the chart, run tests/static checks, and
   inspect rendered RBAC. After an authorized release, verify Argo Synced/Healthy,
   workload Ready, certificate ready, and actual route discovery. Do not claim
   live completion without cluster evidence.

## Rollback

Restore the previous landing-page image/chart values through GitOps. To retire
discovery, revert its workload/RBAC and restore the prior static page; keep the
existing Argo Application, hostname, certificate, and ingress unless retirement
is explicitly intended. No persistent data is involved.

## Open questions / rollout checks

- Confirm discovery handles resourceVersion reconnect/resync and bounded API retry.
- Select and document exact metadata annotation keys and category names; routes
  without metadata must continue to display.
- Determine whether the current landing image/build project can host the runtime
  component conveniently while preserving deployed app identity.
- On release, verify `atlas.lan` DNS, certificate readiness, LAN allowlist, and
  discovery against live Ingress resources.
