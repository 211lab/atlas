# Grafana fleet coverage and email alerting

## Goal

Extend the existing kube-prometheus-stack installation into an explicit,
GitOps-managed monitoring system for known Atlas infrastructure in `10.0.0.0/8`.
Provide Grafana views for nodes, Kubernetes containers, and known devices, with
actionable alerts delivered by email.

## User-visible behavior

- Grafana presents known infrastructure in fleet, Proxmox/guest, Kubernetes,
  network/device, and storage views.
- A central fleet overview compares every currently scraped node and shows
  Kubernetes container resource usage without requiring per-node navigation.
- Prometheus has explicit scrape targets for known systems only. The `10.0.0.0/8`
  range is a scope boundary, not a scan target.
- Alerts for unavailable targets, stale metrics, resource pressure, disk/storage
  thresholds, and failed service probes are sent to the configured email
  recipients.
- Monitoring configuration is versioned in this repository and reconciled by
  GitOps without replacing or losing the existing monitoring release.

## Known target scope

Initial target inventory is derived from `inventory.yml` and
`docs/infrastructure-review.md`:

- Proxmox hosts: Turing `.101`, Hopper `.102`, Lovelace `.103`, Babbage `.104`,
  Memex `.105`, and Minsky `.106`.
- K3s guests: cp1 `.110`, cp2 `.111`, cp3 `.112`, and worker1 `.113`.
- Known guests/services: TrueNAS `.26`, Pi-hole `.10`, Hermes `.1`, plus the
  inventoried Proxmox VMs and LXC where a supported guest exporter can be
  installed.
- Kubernetes container/workload metrics remain provided by kube-prometheus-stack
  and its kubelet/cAdvisor, kube-state-metrics, and node-exporter targets.

The infrastructure review records Node Exporter as active on the four cluster
PVE hosts and inactive on Memex and Minsky. It also notes that TrueNAS pool and
disk health are not currently verified. Network appliances such as router,
switches, access points, and UPSes must be explicitly inventoried before they
can be included; no discovery or automatic target enrollment is part of this
phase.

## Current-state evidence and constraints

Live inspection found kube-prometheus-stack chart `88.3.0` installed as the k3s
`HelmChart` `kube-system/atlas-monitoring`, not tracked by an Argo CD Application.
Its values disable Alertmanager, enable seven-day Prometheus retention on
`emptyDir`, and configure Grafana with an existing admin Secret. The Prometheus
instance selects ServiceMonitors, PodMonitors, PrometheusRules, and ScrapeConfigs
with label `release: atlas-monitoring`. Existing Kubernetes monitoring objects
are present. A live Prometheus targets API check confirmed all four k3s
node-exporter targets (`10.0.0.110`–`.113:9100`) and all four cluster PVE Node
Exporter targets (`10.0.0.101`–`.104:9100`) were `UP`. Grafana is available
in-cluster at `atlas-monitoring-grafana.monitoring.svc.cluster.local:3000` and
published as a LoadBalancer on node addresses `.110`–`.113`, port `3000`. Memex
and Minsky PVE host targets remain absent from that verified scrape set.

Changing Helm ownership is a migration: the current `HelmChart` release must
continue to be the sole owner until a GitOps handoff is proven safe. Do not
install a second chart release or delete the current release as part of the
initial cutover.

## Non-goals

- Scanning, ping-sweeping, or discovering arbitrary addresses in `10.0.0.0/8`.
- Self-updating target inventory or automatically enrolling newly seen devices;
  this is a future phase.
- Installing exporters on devices before their supported installation method,
  access, and resource impact are established.
- Claiming physical disk, RAID, or NAS-pool health from host CPU/memory metrics.
- Changing Prometheus retention or storage durability without a separate
  capacity and storage decision.

## Acceptance criteria

1. The monitoring release has a GitOps ownership and reconciliation path that
   preserves its current version, release identity, existing dashboards,
   selectors, resource sizing, and Grafana admin Secret.
2. A committed target inventory covers each approved known endpoint and labels
   it by host/device type and role; no scan-based target generation exists.
3. Prometheus reports expected targets as `UP`; unsupported or unreachable
   targets are explicitly documented with an owner/action rather than hidden.
4. Grafana has usable fleet, Proxmox/guest, Kubernetes/container, network/device,
   and storage views, limited to the signals actually collected. The fleet
   overview includes all currently scraped nodes and container usage together.
5. Alertmanager routes the agreed alert classes to the agreed email recipients;
   SMTP credentials are provided only through a SealedSecret, and an end-to-end
   test email is received.
6. Alert rules are checked for valid PromQL and tested with a controlled test
   alert; firing and resolved notifications are verified.
7. No plaintext credentials, SMTP passwords, or private keys are committed.

## Implementation sequence

1. Reconcile live Prometheus targets and scrape configuration; establish the
   exact currently working PVE target set and identify exporters for the known
   but currently uncovered targets.
2. Inventory known network appliances and SNMP-capable devices with explicit
   addresses and supported read-only telemetry. Add only approved targets.
3. Define the migration of `kube-system/atlas-monitoring` into repository
   ownership without duplicate Helm releases or destructive recreation.
4. Configure static known targets and exporter/blackbox probes using the
   existing Prometheus Operator selection model. Add exporters via the
   appropriate host automation or GitOps app, not manual cluster edits.
5. Enable Alertmanager email delivery after SMTP relay, port/TLS mode, sender,
   recipient list, and credential source are supplied. Store credentials in a
   namespace-scoped SealedSecret.
6. Add dashboards and alert rules, render/validate chart values and manifests,
   and test from Prometheus through Alertmanager to a real inbox.
7. Document actual target coverage and remaining unsupported endpoints in the
   infrastructure review/runbook.

## Open questions

- Which SMTP relay hostname/port and TLS mode should Alertmanager use, and what
  sender and recipient addresses should it use?
- What authentication/credential source is available for that relay, and can a
  SealedSecret be produced in the monitoring namespace?
- Which router, switches, access points, UPSes, and other network devices are
  in the known-device inventory, and which expose SNMP or another metrics API?
- Which known Proxmox guests should receive guest-level exporters? TrueNAS
  exporter/API access and available pool/disk metrics also need confirmation.
- Should monitoring ownership migration and exporter installation be performed
  in a maintenance window, given Prometheus/Grafana are currently ephemeral and
  running as a k3s HelmChart?
