# Software install backlog

Planned applications for Atlas, triaged here before they become specs and charts.
This page is the **triage surface**; each item that is ready to build gets a
`docs/specs/<app>.md` contract and then a Helm chart plus Argo CD Application.

- Delivery and conventions: [`CONTRIBUTING.md`](https://github.com/211lab/atlas/blob/main/CONTRIBUTING.md),
  [`AGENTS.md`](https://github.com/211lab/atlas/blob/main/AGENTS.md).
- Onboarding procedure: [Atlas deploy an application](https://github.com/211lab/atlas/blob/main/.opencode/skills/atlas-deploy-app/SKILL.md).
- Already deployed: [Atlas applications](applications.md).

## How to use this page

- An item is **ready** when it names a style, database/storage, ingress, and any
  hardware dependency, and has a spec under `docs/specs/`.
- Prefer the existing patterns: upstream chart + pinned `helm/values/<name>.yaml`,
  or in-repo `apps/<app>/chart`. Postgres is provided by CloudNativePG (CNPG).
- Secrets are SealedSecrets only. Never commit plaintext credentials or API keys.
- All LAN ingresses use `atlas-ca` TLS and the Traefik `10.0.0.0/8` ipallow
  middleware, matching `redop` and `home-assistant`.

## Legend

| Style | Meaning |
| --- | --- |
| **Cluster-chart** | Upstream Helm chart pinned in `gitops/apps/<name>.yaml`, values in `helm/values/<name>.yaml` (via the `$values` ref). |
| **Cluster-in-repo** | In-repo chart under `apps/<app>/chart`, referenced by `gitops/apps/<app>.yaml`. |
| **Operator-backed** | Requires a cluster operator (currently CNPG for PostgreSQL). |
| **Edge/hardware** | Cannot run as a cluster service without host/device access; deprioritized. |
| **SPIKE** | Needs research before it can be planned. |

## Backlog

| App | What it is | Style | DB / storage | Ingress | Wave | Spec |
| --- | --- | --- | --- | --- | --- | --- |
| **Atlas landing page** | Root-domain graffiti wordmark "Atlas" | Cluster-in-repo (static nginx) | none | `atlas.lan` (apex) + `www.atlas.lan` | 1 | [spec](specs/atlas-landing.md) |
| **code-server** | VS Code in the browser | Cluster-in-repo (upstream image) | workspace PVC (`truenas-nfs`) | `code.atlas.lan` | 1 | [spec](specs/code-server.md) |
| **n8n** | Workflow automation | Cluster-in-repo + CNPG | CNPG Postgres + `.n8n` PVC | `n8n.atlas.lan` | 1 | [spec](specs/n8n.md) |
| **Paperclip** | Open-source AI agent orchestration ("a company of agents") | Cluster-in-repo (upstream image) | CNPG Postgres + `PAPERCLIP_HOME` PVC | `paperclip.atlas.lan` | 2 | [spec](specs/paperclip.md) |
| **Nextcloud** | File sync and collaboration | Cluster-chart + CNPG | CNPG Postgres + Redis + data PVC (NFS RWX) | `cloud.atlas.lan` | 2 | [spec](specs/nextcloud.md) |
| **Paperless-ngx** | Document management with OCR (scans, receipts, mail import) | Cluster-in-repo + CNPG | CNPG Postgres + valkey broker + media/consume PVCs (NFS) | `paperless.atlas.lan` | 2 | [spec](specs/paperless-ngx.md) |
| **Frigate** | Network video recorder for cameras | Edge/hardware (deprioritized) | recordings PVC (large, NFS) | `frigate.atlas.lan` (TBD) | 3 | — |
| **MagicMirror²** | Smart-mirror dashboard | Edge/hardware (deprioritized) | none (runs at the display) | n/a | 3 | — |

## Waves

Sequencing is driven by the cluster's real constraints: memory is the tight
resource (control planes already run hot; a single worker node carries most
pods), stateful data uses `truenas-nfs`, and `*.atlas.lan` DNS is not yet live.

| Wave | Apps | Rationale |
| --- | --- | --- |
| **1** | atlas-landing, code-server, n8n | Low-to-moderate footprint; landing page has no state; code-server and n8n unlock daily use. |
| **2** | paperclip, nextcloud, paperless-ngx | Stateful and/or heavy; each adds a CNPG cluster; validate the memory budget after Wave 1. |
| **3** | frigate, magicmirror | Hardware/edge-bound; tracked here but not cluster services today. |

### Wave 3 notes (edge/hardware, deprioritized)

- **Frigate** needs camera RTSP reachability and, for a practical deployment,
  a Coral USB or GPU for object detection. That hardware requires host-device
  passthrough, which Atlas does not currently provide; CPU-only detection is
  resource-heavy on the single worker. Revisit only if a dedicated node or
  accelerator is added.
- **MagicMirror²** is display-bound. Its value is a screen at the mirror, so it
  belongs on a small edge host (for example a Raspberry Pi), not the cluster. A
  cluster deployment would only serve its web UI and is not the intended use.

## In progress

| Item | Where |
| --- | --- |
| Home Assistant | branch `feat/home-assistant-deployment`; [spec](specs/home-assistant.md) |
| Atlas docs site (`docs.atlas.lan`) | [spec](specs/docs-site-and-infrastructure-review.md); untracked working tree changes |

## Cross-cutting prerequisites

These apply across the backlog and should be resolved before or alongside the
waves that depend on them.

- **DNS and reachability.** ADR 0001 is accepted and declared but not live: the
  Pi-hole host (`10.0.0.107`) is unprovisioned and the ExternalDNS SealedSecret
  is a placeholder. Until then new `.atlas.lan` hosts resolve only in-cluster
  (CoreDNS `coredns-custom`) and via workstation `/etc/hosts` entries.
- **PostgreSQL.** Use the CNPG operator (`gitops/apps/cnpg.yaml`) for every app
  database so backup, failover, and credentials follow one pattern.
- **Storage.** Stateful data belongs on `truenas-nfs` (RWX-capable); `local-path`
  is for ephemeral/node-local data. Storage classes are immutable.
- **Images and registry.** App images are built by Gitea Actions and pulled with
  a namespace-local `gitea-registry` SealedSecret; never hand-edit promoted tags.
- **Memory budget.** Set realistic `requests`/`limits`; control-plane memory
  limits are already overcommitted. Review `kubectl top` before each new wave.
- **Exposure.** Internal `atlas-ca` TLS plus the `10.0.0.0/8` Traefik ipallow
  middleware on every LAN ingress. No public exposure.

## Definition of done (per app)

An item is complete when all of the following hold:

1. A pinned chart (or pinned upstream chart + values) exists and renders.
2. An Argo CD Application in project `platform` reconciles it `Synced/Healthy`.
3. The ingress serves over HTTPS with an `atlas-ca` certificate and the LAN
   allowlist; clients outside `10.0.0.0/8` are denied.
4. Any stateful data survives a pod restart/reschedule on `truenas-nfs`.
5. Secrets are SealedSecrets; no plaintext credential or key is in git.
6. The app's spec under `docs/specs/` records verified status, or explicitly
   marks what remains unverified.
