# Atlas documentation

Atlas is the lab's Proxmox-backed k3s and GitOps platform. Start with the
[infrastructure review](infrastructure-review.md) for dated live evidence,
declared state, risks and unavailable information. Runbooks are operational
instructions, not continuously refreshed health reports.

## Infrastructure and architecture

- [Infrastructure review: hosts, guests, tenants and findings](infrastructure-review.md)
- [Architecture overview](c4-architecture.md)
- [Physical placement and failure domains](architecture/placement.md)
- [Application dependencies](architecture/application-dependencies.md)
- [Kubernetes control-plane access and recovery](kubernetes-control-plane.md)

## Platform and applications

- [GitOps platform](gitops-platform.md)
- [Application catalog](applications.md)
- [Software install backlog](backlog.md)
- [Immich operations and recovery](runbooks/immich.md)
- [Sealing secrets](sealing-secrets.md)

## Naming and access

- [DNS architecture](atlas-dns.md)
- [Dedicated Pi-hole design](pihole-dns.md)
- [Pi-hole operational runbook](pihole-runbook.md)
- [Client trust for the Atlas root certificate](runbooks/client-trust.md)
- [ADR 0001: service naming and reachability](adr/0001-service-naming-and-reachability.md)

## Documentation delivery

- [Build, publish, release and roll back this site](docs-publishing.md)
- [Documentation site and infrastructure review specification](specs/docs-site-and-infrastructure-review.md)

The canonical site is `https://docs.atlas.lan/`. It is live since
2026-10-11 (the 2026-10-07 collection had found no docs ingress and HTTP 404;
that is superseded). Publishing changes are gated by the
prerequisites in the [publishing runbook](docs-publishing.md).
