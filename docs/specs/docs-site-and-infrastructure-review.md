# Atlas documentation site and infrastructure review

## Goal

Serve the Atlas documentation as a MkDocs build at **https://docs.atlas.lan** and provide a comprehensive, evidence-based review of physical infrastructure, Proxmox guests, k3s tenants, platform software, and applications, emphasizing small relationship diagrams.

## User-visible behavior

- A searchable MkDocs Material site publishes the Markdown in `docs/`, with a landing page linking grouped infrastructure, tenant/application, architecture, and operational documentation.
- The canonical hostname is `docs.atlas.lan`; `doc.atlas.lan` is not configured.
- Prefer diagrams for topology, ownership, placement, dependencies, and delivery paths. **Every diagram contains at most five elements.** Labels and connections do not count. Nodes, participants, and visible grouping containers do count. Split larger views into linked, focused diagrams rather than hiding extra elements in groups.
- Inventory records distinguish live observations, repository declarations, historical claims, and inaccessible/unverified resources. Review findings describe evidence and impact, not automatic remediation.
- Retain existing runbooks and ADR intent; update stale topology descriptions only with evidence, and preserve useful operational detail when splitting diagrams.

## Scope and assumptions

- ASSUMPTION: The existing `atlas` repository owns the docs sources, build, and GitOps deployment; a separate forge repository is unnecessary.
- ASSUMPTION: “k3s tenants” means all observed namespaces and their workloads, including platform namespaces, rather than inventing a multi-tenant isolation scheme.
- ASSUMPTION: “all Proxmox hosts” includes every host in the repository inventory. Non-Proxmox machines remain visible and are explicitly classified; unreachable hosts are included with the access gap, never omitted.
- ASSUMPTION: Existing authorized SSH and kubeconfig access may be used for read-only inspection. No infrastructure, guest, workload, DNS, or secret changes are authorized by this review.
- ASSUMPTION: Internal Atlas CA TLS and existing wildcard DNS are appropriate; public exposure and public certificates are not requested.
- ASSUMPTION: Existing diagrams throughout published docs must also meet the five-element limit, not only newly authored diagrams.
- Build output and temporary tooling live outside the checkout under `/tmp/opencode`; no generated site, dependency tree, or build output is tracked.

## Non-goals

- Repairing unrelated drift, upgrading software, provisioning machines, restarting services, migrating storage, or testing destructive recovery.
- Publishing credentials, kubeconfigs, secret data, raw guest configuration with credentials, or personal application data.
- Public internet publishing, a new authentication service, or a new infrastructure inventory platform.
- Committing, pushing, tagging releases, or creating PRs without explicit user authorization. Deployment through GitOps remains gated on that authorization and existing CI credentials.

## Acceptance criteria

1. **Build:** Given a clean checkout and pinned docs dependencies, when the documented MkDocs build command runs, then it produces the complete static site outside the repository, with search and Mermaid support, and no broken newly introduced internal links or unhandled build warnings.
2. **Hostname and deployment:** Given the docs Helm chart, when rendered with defaults, then it contains a stateless resource-bounded HTTP Deployment, Service, and Traefik HTTPS Ingress for `docs.atlas.lan` using `atlas-ca`, and an Argo Application in project `platform` sourced from the existing Gitea `atlas` main branch. No persistent storage is required.
3. **Delivery:** Given an authorized publishing change, when the docs CI runs, then it checks/builds the site, publishes an immutable image, and promotes the resulting tag through GitOps without a commit/build loop. Document required CI secrets, registry-pull provisioning, release/rollback steps, and any absent prerequisites rather than claiming deployment success.
4. **Host coverage:** Given the repository machine inventory and reachable Proxmox APIs/SSH, when the review is read, then every inventoried host is classified with observed or declared role, version/capacity where accessible, guest/cluster relationships, evidence date/source, and explicit gaps. All observed Proxmox VMs/LXCs are accounted for without disclosing secrets.
5. **Tenant/application coverage:** Given read-only Kubernetes access and declared Argo Applications, when the review is read, then all observed namespaces, applications, and platform components are accounted for, with workload/version, ingress, storage, placement/dependency, health/drift, and security/recovery observations where evidence permits. Missing evidence is labeled.
6. **Diagram limit:** Given every diagram in published Markdown, when independently counted, then no diagram has more than five entities plus visible grouping containers (excluding labels/edges). Diagrams render in the built site's Mermaid integration; large views are split with nearby text/links explaining their relations.
7. **Review integrity:** Given conflicting older documents or inaccessible systems, when findings are reported, then declared and observed state are differentiated, uncertainties and access gaps remain explicit, and no unrelated runtime changes have been made.
8. **Live completion gate:** Given authorized commits/pushes and available CI/registry credentials, when GitOps converges, then Argo reports docs Synced/Healthy, the Deployment is Ready, the certificate is ready, and `https://docs.atlas.lan/` returns the built landing page. Otherwise report this criterion as blocked, with precise prerequisites; DNS or rendered manifests alone do not satisfy it.

## Ordered implementation plan and responsible layers

1. **Specification (this file):** establish constraints, source-of-truth, and acceptance. Verification: compare scope against the request and existing operational contract.
2. **Publishing layer:** add `mkdocs.yml`, `requirements-docs.txt`, `apps/docs/Dockerfile`, `apps/docs/chart/`, `gitops/apps/docs.yaml`, `.gitea/workflows/docs.yaml`, and `docs/docs-publishing.md`; use existing dave-study chart and forge CI patterns. Build from root docs without copying unrelated repository contents into the image. Verification: MkDocs build, Docker build/HTTP smoke, Helm rendering, workflow trigger/promotion inspection. Avoid modifying review pages in this task.
3. **Documentation/review layer:** add `docs/index.md`, `docs/infrastructure-review.md` and focused `docs/architecture/` pages as needed; inspect inventory, Proxmox hosts/guests, all k3s namespaces/workloads, ingress/storage/Argo state read-only. Update `docs/c4-architecture.md`, DNS diagrams, ADR diagrams, `docs/applications.md`, and stale operational descriptions only as necessary. Verification: inventory coverage tables and source citations, all diagrams <=5 elements, preserved links and runbook intent. Coordinate navigation through landing-page links rather than modifying publishing-layer configuration.
4. **Independent verification:** build with pinned dependencies; check image serving, manifests, inventory coverage, link integrity, and manually audit each diagram's count/rendering. Record failed or blocked criteria precisely and return scoped defects to the responsible implementer.
5. **Authorized release:** only after explicit commit/push permission, publish via existing GitOps; verify live criterion 8. Without permission, leave reviewable files and a deployment handoff.

## Rollback

- Before release: revert only files introduced/changed for this spec, preserving unrelated workspace changes.
- After release: revert the docs image promotion to the previous immutable tag through GitOps. To retire the new service, remove `gitops/apps/docs.yaml` through an authorized GitOps change; Argo prunes only docs resources. No persistent data is involved.
- Documentation edits can be reverted independently of the publishing chart.

## Open questions / release gates

- Release authorization received from the user (“Do it”) after the explicit request to commit/push to Atlas Gitea, provision required publishing credentials, and verify live deployment. Only docs-related credential setup and GitOps deployment are authorized; unrelated remediation remains excluded.
- Release implementation includes `apps/docs/chart/templates/registry-sealed-secret.yaml`: a namespace-bound `docs/gitea-registry` SealedSecret reconciled by the docs chart. `gitops/sealed/` alone is not a reconciled source. Use dedicated scoped publishing credentials where supported, never print or commit plaintext credentials.
- Registry evidence: Gitea 1.27.0 permits replacing container tags. To satisfy the immutable delivery criterion without a global registry change, CI must promote the pushed image's verified registry digest into docs chart values, and the Deployment must select `repository@sha256:…` for released images. Unique run tags remain provenance labels, not the immutability guarantee. Verification must check digest extraction/validation, atomic tag+digest promotion, and live image digest selection. Rollback selects the previous digest through GitOps.
- Preserve the intervening forge commit `2a08871` (Redop CI promotion): the checkout was one commit behind Gitea at release reconnaissance. Reconcile with a non-destructive fast-forward/merge before publishing; no force-push or unrelated tag rollback.

- Verification follow-up in scope: fix the existing out-of-tree link in `docs/pihole-runbook.md` using a published documentation target, and repair Mermaid built-site initialization in the publishing layer. Standalone SVG rendering does not satisfy the built-site diagram criterion.

- Explicit permission to commit/push the publishing changes and release via Gitea has been granted; live completion still requires the checks above.
- Verify existing Gitea Actions credential names and namespace-local registry pull-secret provisioning; do not expose or fabricate credentials.
- Reachability/authorization of every inventoried Proxmox/standalone host is unproven until read-only inspection.
- Existing DNS resolves docs.atlas.lan but live reconnaissance found no docs ingress and an HTTP 404; the service is not yet deployed.
